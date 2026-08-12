#!/usr/bin/env python
"""Synthetic landing-zone generator for the tradeflow warehouse.

Produces Hive-partitioned Parquet under ``data/landing/`` shaped like the daily
extracts a brokerage's ingestion tool would drop into object storage. The dbt
project reads those files as external sources, so the warehouse never sees this
module -- it only sees files, exactly as it would in production.

Three properties are load-bearing, and each one exists to make something
downstream demonstrable rather than decorative:

*Deterministic.* Given the same ``--seed``, ``--scale`` and date range the
output is byte-stable, so CI can assert exact row counts and the dbt tests mean
something. Determinism is per ``(seed, scale, date range)``: changing the scale
changes the batch layout and therefore the random draws.

*Scale-configurable.* ``--scale`` moves row counts across four orders of
magnitude without touching a single model, which is what makes the incremental
models and partition pruning necessary instead of ornamental.

*Deliberately imperfect.* ``--inject-anomalies`` plants real defects -- duplicate
fills, orphan foreign keys, negative quantities, over-fills, out-of-window
timestamps, missing PII. The data quality tests exist to catch these, and a test
suite that has never caught anything proves nothing.

Everything here is invented. See ``reference_data.py`` for what is real-world
(instrument metadata) and what is not (prices, and all customer data).

Usage::

    python -m ingestion.generate --scale small --seed 42
    python -m ingestion.generate --scale tiny --inject-anomalies
    python -m ingestion.generate --customers 5000 --days 400 --no-events
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from faker import Faker

# Allow both `python -m ingestion.generate` and `python ingestion/generate.py`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.reference_data import (
    ACCOUNT_TYPES,
    APP_EVENT_TYPES,
    CHANNELS,
    COUNTRIES,
    CUSTOMER_TIERS,
    DEVICE_FAMILIES,
    FX_PAIRS,
    INSTRUMENT_COLUMNS,
    INSTRUMENTS,
    MARKET_HOLIDAYS,
    ORDER_STATUSES,
    ORDER_TYPES,
    PAYMENT_METHODS,
    REPORTING_CURRENCY,
    VENUES,
)

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

#: Scale presets. ``customers`` and ``days`` are the only knobs that move; every
#: other rate is a per-entity constant, so row counts scale predictably.
SCALE_PRESETS: dict[str, dict[str, int]] = {
    "tiny": {"customers": 250, "days": 120},
    "small": {"customers": 2_500, "days": 400},
    "medium": {"customers": 25_000, "days": 730},
    "large": {"customers": 150_000, "days": 1_095},
}

#: Customers are generated in blocks so peak memory stays flat as scale grows.
#: Every downstream entity for a block is generated and written before the next
#: block starts, which is why ``large`` runs on a laptop. 10,000 keeps peak
#: resident memory near 2 GB; 25,000 measured at 4.6 GB for no gain in speed.
#: Changing this changes the random draws, so output is reproducible per
#: ``(seed, scale)`` rather than per seed alone.
CUSTOMER_BLOCK_SIZE = 10_000

#: Trading-activity segments: (name, weight, orders per active day, notional mean).
#: A small number of customers generate most of the order flow, which is what
#: makes the aggregate marts and the customer-performance charts non-uniform.
SEGMENTS: list[tuple[str, int, float, float]] = [
    ("whale", 3, 1.20, 24_000.0),
    ("active", 17, 0.35, 6_500.0),
    ("casual", 50, 0.08, 1_800.0),
    ("dormant", 30, 0.01, 900.0),
]

#: Share of orders that are buys. Shared by the order generator and the cash
#: generator: the funding model is derived from it, and if the two drifted apart
#: every account would end the window either starved of cash or absurdly rich.
BUY_PROBABILITY = 0.62

#: Order notional is drawn as ``segment_mean x lognormal(0, NOTIONAL_SIGMA)``.
#: The mean of that multiplier is ``exp(sigma^2 / 2)``, not 1 -- a lognormal's
#: mean sits above its median. Funding the expected notional without this factor
#: under-funds every account by 28%.
NOTIONAL_SIGMA = 0.7
NOTIONAL_MEAN_FACTOR = float(np.exp(NOTIONAL_SIGMA**2 / 2))

#: How much more an account is funded than its expected net investment. Real
#: customers keep a cash buffer, and the buffer also has to absorb Poisson
#: variance in order counts: an account whose orders happen to cluster early
#: would otherwise overdraw before its recurring deposits arrive.
FUNDING_BUFFER = 2.2

#: Sessions per active day, by segment, for the app-event stream.
SEGMENT_ENGAGEMENT: dict[str, float] = {
    "whale": 0.85,
    "active": 0.40,
    "casual": 0.12,
    "dormant": 0.02,
}

ENTITIES_PARTITIONED_BY_DATE = {
    "customer_extracts": "extract_date",
    "orders": "placed_date",
    "executions": "executed_date",
    "cash_movements": "occurred_date",
    "app_events": "event_date",
}

ENTITIES_PARTITIONED_BY_MONTH = {
    "market_prices": "price_month",
    "fx_rates": "rate_month",
}


@dataclass
class Config:
    """Resolved generation parameters."""

    customers: int
    days: int
    seed: int
    end_date: date
    out_dir: Path
    inject_anomalies: bool = False
    include_events: bool = True
    scale_name: str = "custom"

    @property
    def start_date(self) -> date:
        return self.end_date - timedelta(days=self.days - 1)


@dataclass
class Stats:
    """Row counts and timings, written to the landing-zone manifest."""

    rows: dict[str, int] = field(default_factory=dict)
    anomalies: dict[str, int] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    def add(self, entity: str, n: int) -> None:
        self.rows[entity] = self.rows.get(entity, 0) + n


# --------------------------------------------------------------------------- #
# Small vectorised helpers
# --------------------------------------------------------------------------- #


def weighted_pick(
    rng: np.random.Generator, choices: list[tuple], size: int, value_index: int = 0
) -> np.ndarray:
    """Draw ``size`` values from ``(value, ..., weight)`` tuples by weight.

    The weight is always the last element of each tuple, which keeps the
    reference-data literals readable.
    """
    values = [c[value_index] for c in choices]
    weights = np.array([c[-1] for c in choices], dtype=float)
    probabilities = weights / weights.sum()
    return rng.choice(values, size=size, p=probabilities)


def zero_padded_ids(prefix: str, start: int, count: int) -> np.ndarray:
    """Build ``PREFIX-0000000042``-style identifiers without a Python loop."""
    numbers = np.arange(start, start + count, dtype=np.int64)
    return np.char.add(f"{prefix}-", np.char.zfill(numbers.astype("U10"), 10))


def split_quantity(
    rng: np.random.Generator, totals: np.ndarray, parts: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Split each total into ``parts`` positive pieces that sum exactly to it.

    Used to break an order's filled quantity into individual executions. Returns
    ``(group_index, piece)`` where ``group_index`` maps each piece back to its
    order. Exactness matters: the ``executions sum to order quantity`` test is
    one of the warehouse's core invariants, so an off-by-rounding split here
    would show up as a false positive there.
    """
    group_index = np.repeat(np.arange(len(totals)), parts)
    # One unit to every piece, then distribute what is left by random weights.
    base = np.ones(len(group_index))
    remaining = totals - parts
    weights = rng.random(len(group_index)) + 0.05
    weight_sums = np.bincount(group_index, weights=weights, minlength=len(totals))
    share = weights / weight_sums[group_index]
    extra = np.floor(remaining[group_index] * share)
    pieces = base + extra
    # Rounding always leaves a little on the table; give it to each group's
    # first piece so the sum is exact.
    allocated = np.bincount(group_index, weights=pieces, minlength=len(totals))
    shortfall = totals - allocated
    first_of_group = np.concatenate(([0], np.cumsum(parts)[:-1]))
    pieces[first_of_group] += shortfall
    return group_index, pieces


def u_shaped_seconds(
    rng: np.random.Generator, size: int, span_seconds: int
) -> np.ndarray:
    """Intraday offsets clustered at the open and the close.

    Real order flow is U-shaped across the session; a uniform draw would flatten
    the hour-of-day charts into noise.
    """
    return (rng.beta(0.65, 0.65, size=size) * span_seconds).astype(np.int64)


def to_ip_addresses(rng: np.random.Generator, size: int) -> np.ndarray:
    """Plausible public IPv4 strings. Classified as PII downstream."""
    octets = rng.integers(1, 255, size=(size, 4))
    octets[:, 0] = rng.choice([13, 20, 24, 49, 58, 72, 101, 121, 203], size=size)
    return np.array(
        [".".join(map(str, row)) for row in octets],
        dtype=object,
    )


# --------------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------------- #


def dictionary_encode(
    frame: pd.DataFrame, skip: set[str] | None = None, sample: int = 10_000
) -> pd.DataFrame:
    """Convert repeated string columns to a categorical dtype before writing.

    Columns like ``user_agent``, ``venue`` and ``event_type`` repeat a handful of
    long values across millions of rows. As pandas ``object`` columns each row
    holds its own Python string; as ``category`` they collapse to an integer
    code plus a dictionary, and PyArrow carries that straight through to
    Parquet's dictionary encoding -- smaller files and materially lower peak
    memory for no loss of fidelity.

    Cardinality is judged from a sample rather than the full column: an exact
    ``nunique`` over ten object columns of a multi-million-row frame costs more
    than the encoding saves. A false negative here is merely a missed
    optimisation, so a cheap heuristic is the right trade.

    ``skip`` exempts the Hive partition column. Arrow cannot sort a dictionary
    column, and the partition value is encoded in the directory path rather than
    stored in the file, so encoding it would break the write for no benefit.
    """
    skip = skip or set()
    encoded = frame.copy(deep=False)
    head = encoded.head(sample)
    for column in encoded.columns:
        if column in skip or encoded[column].dtype != object:
            continue
        if head[column].map(type).eq(str).all() and head[column].nunique() <= 64:
            encoded[column] = encoded[column].astype("category")
    return encoded


class LandingZone:
    """Writes Hive-partitioned Parquet, appending across customer blocks."""

    def __init__(self, root: Path, stats: Stats) -> None:
        self.root = root
        self.stats = stats
        self._file_counter: dict[str, int] = {}

    def write(self, entity: str, frame: pd.DataFrame) -> None:
        if frame.empty:
            self.stats.add(entity, 0)
            return

        partition_column = ENTITIES_PARTITIONED_BY_DATE.get(
            entity
        ) or ENTITIES_PARTITIONED_BY_MONTH.get(entity)

        target = self.root / entity
        target.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(
            dictionary_encode(
                frame, skip={partition_column} if partition_column else None
            ),
            preserve_index=False,
        )
        sequence = self._file_counter.get(entity, 0)
        self._file_counter[entity] = sequence + 1

        if partition_column:
            # Sorting by the partition key first is what keeps this cheap. The
            # dataset writer holds a file handle open per partition it is
            # actively writing; with sorted input each partition is contiguous,
            # so exactly one handle is ever open and we get one file per
            # partition per block instead of a scattering of fragments.
            #
            # max_partitions has to be raised explicitly: pyarrow's default of
            # 1024 is a safety valve, and 1,095 days of daily partitions walks
            # straight into it.
            table = table.sort_by(partition_column)
            pq.write_to_dataset(
                table,
                root_path=str(target),
                partition_cols=[partition_column],
                basename_template=f"part-{sequence:04d}-{{i}}.parquet",
                existing_data_behavior="overwrite_or_ignore",
                max_partitions=4096,
                max_open_files=64,
                compression="zstd",
            )
        else:
            pq.write_table(
                table, target / f"part-{sequence:04d}.parquet", compression="zstd"
            )

        self.stats.add(entity, len(frame))


# --------------------------------------------------------------------------- #
# Calendars, instruments, prices
# --------------------------------------------------------------------------- #


def build_calendar(config: Config) -> pd.DataFrame:
    """Every calendar day in range, flagged as a trading day or not.

    Crypto trades on all of them; everything else observes weekends and the
    holiday list. Orders placed while a market is shut roll to the next session,
    which is both what real brokers do and a nice source of Monday seasonality.
    """
    days = pd.date_range(config.start_date, config.end_date, freq="D")
    holidays = pd.to_datetime(MARKET_HOLIDAYS)
    is_weekday = days.dayofweek < 5
    is_trading_day = is_weekday & ~days.isin(holidays)

    calendar = pd.DataFrame(
        {
            "calendar_date": days,
            "day_index": np.arange(len(days)),
            "is_trading_day": is_trading_day,
        }
    )
    # For each calendar day, the index of the session an order placed that day
    # would actually execute in.
    sessions = pd.Series(
        np.where(is_trading_day, calendar["day_index"], np.nan), dtype="float64"
    )
    # bfill rolls a closed day forward to the next session. Trailing closed days
    # have no next session inside the window, so they fall back to the previous
    # one -- otherwise they would resolve to the last day in range, which may
    # itself be a weekend.
    calendar["next_session_index"] = sessions.bfill().ffill().astype(np.int64)
    return calendar


def build_instruments(rng: np.random.Generator) -> pd.DataFrame:
    """Instrument reference table, one row per tradeable symbol."""
    frame = pd.DataFrame(INSTRUMENTS, columns=INSTRUMENT_COLUMNS)
    frame.insert(0, "instrument_id", zero_padded_ids("INS", 1, len(frame)))
    frame["is_active"] = True
    # A couple of delistings so the warehouse has to cope with inactive
    # instruments that still carry historical fills.
    delisted = rng.choice(frame.index, size=2, replace=False)
    frame.loc[delisted, "is_active"] = False
    frame["listed_date"] = pd.Timestamp("2010-01-04")
    frame["ingested_at"] = pd.Timestamp.now(tz=UTC)
    return frame


def build_fx_rates(rng: np.random.Generator, calendar: pd.DataFrame) -> pd.DataFrame:
    """Daily rates against the reporting currency, one row per pair per day.

    FX is quoted every calendar day (including weekends, carried forward) so the
    warehouse can always convert a fill without a gap-filling join.
    """
    frames = []
    n_days = len(calendar)
    for base, quote, start_rate, annual_volatility in FX_PAIRS:
        daily_volatility = annual_volatility / np.sqrt(252)
        shocks = rng.normal(0.0, daily_volatility, size=n_days)
        path = start_rate * np.exp(np.cumsum(shocks - 0.5 * daily_volatility**2))
        frames.append(
            pd.DataFrame(
                {
                    "base_currency": base,
                    "quote_currency": quote,
                    "rate_date": calendar["calendar_date"].values,
                    "rate": np.round(path, 6),
                }
            )
        )
    # The reporting currency against itself, so downstream joins never special-case.
    frames.append(
        pd.DataFrame(
            {
                "base_currency": REPORTING_CURRENCY,
                "quote_currency": REPORTING_CURRENCY,
                "rate_date": calendar["calendar_date"].values,
                "rate": 1.0,
            }
        )
    )
    rates = pd.concat(frames, ignore_index=True)
    rates["rate_month"] = rates["rate_date"].dt.strftime("%Y-%m")
    rates["ingested_at"] = pd.Timestamp.now(tz=UTC)
    return rates


def build_market_prices(
    rng: np.random.Generator, instruments: pd.DataFrame, calendar: pd.DataFrame
) -> tuple[pd.DataFrame, np.ndarray]:
    """Simulated OHLCV per instrument per day.

    Returns the long-format price table for the landing zone, plus the dense
    ``(instrument, day)`` close-price matrix the order generator prices against.
    Prices follow a geometric Brownian motion -- realistic in shape, and not
    market data. Non-crypto instruments are dropped on non-trading days *after*
    the walk, so a Monday close follows the previous Friday rather than a
    fabricated weekend.
    """
    n_instruments = len(instruments)
    n_days = len(calendar)
    daily_drift = instruments["annual_drift"].to_numpy()[:, None] / 252.0
    daily_volatility = instruments["annual_volatility"].to_numpy()[:, None] / np.sqrt(252)

    shocks = rng.normal(0.0, 1.0, size=(n_instruments, n_days))
    log_returns = (daily_drift - 0.5 * daily_volatility**2) + daily_volatility * shocks
    closes = instruments["start_price"].to_numpy()[:, None] * np.exp(
        np.cumsum(log_returns, axis=1)
    )

    previous_closes = np.hstack(
        [instruments["start_price"].to_numpy()[:, None], closes[:, :-1]]
    )
    overnight_gap = rng.normal(0.0, 0.3, size=closes.shape) * daily_volatility
    opens = previous_closes * (1.0 + overnight_gap)
    intraday_range = np.abs(rng.normal(0.0, 1.0, size=closes.shape)) * daily_volatility
    highs = np.maximum(opens, closes) * (1.0 + intraday_range)
    lows = np.minimum(opens, closes) * (1.0 - intraday_range)
    volumes = (
        rng.lognormal(mean=14.0, sigma=1.1, size=closes.shape)
        * instruments["popularity"].to_numpy()[:, None]
        / 50.0
    )

    is_crypto = (instruments["asset_class"] == "crypto").to_numpy()
    tradeable = np.where(
        is_crypto[:, None],
        True,
        calendar["is_trading_day"].to_numpy()[None, :],
    )

    instrument_axis, day_axis = np.nonzero(tradeable)
    prices = pd.DataFrame(
        {
            "instrument_id": instruments["instrument_id"].to_numpy()[instrument_axis],
            "symbol": instruments["symbol"].to_numpy()[instrument_axis],
            "price_date": calendar["calendar_date"].to_numpy()[day_axis],
            "open_price": np.round(opens[instrument_axis, day_axis], 4),
            "high_price": np.round(highs[instrument_axis, day_axis], 4),
            "low_price": np.round(lows[instrument_axis, day_axis], 4),
            "close_price": np.round(closes[instrument_axis, day_axis], 4),
            "previous_close_price": np.round(
                previous_closes[instrument_axis, day_axis], 4
            ),
            "volume": volumes[instrument_axis, day_axis].astype(np.int64),
            "currency": instruments["currency"].to_numpy()[instrument_axis],
        }
    )
    prices["price_month"] = pd.to_datetime(prices["price_date"]).dt.strftime("%Y-%m")
    prices["ingested_at"] = pd.Timestamp.now(tz=UTC)
    return prices, closes


# --------------------------------------------------------------------------- #
# Customers
# --------------------------------------------------------------------------- #


def build_identity_pool(seed: int, size: int = 4_000) -> pd.DataFrame:
    """A reusable pool of fake identities.

    Faker costs roughly 40 microseconds per field, which is fine for 4,000 rows
    and ruinous for 150,000. Sampling a pool with replacement and making the
    unique fields unique by construction (email carries the customer number)
    keeps generation linear while leaving the PII surface realistic. This is a
    deliberate trade and the reason no two customers share an email.
    """
    faker = Faker(["en_US", "en_AU", "en_GB"])
    Faker.seed(seed)
    return pd.DataFrame(
        {
            "first_name": [faker.first_name() for _ in range(size)],
            "last_name": [faker.last_name() for _ in range(size)],
            "street_address": [faker.street_address() for _ in range(size)],
            "city": [faker.city() for _ in range(size)],
            "postcode": [faker.postcode() for _ in range(size)],
        }
    )


def build_customers(
    rng: np.random.Generator,
    config: Config,
    identities: pd.DataFrame,
    block_start: int,
    block_size: int,
) -> pd.DataFrame:
    """Base customer attributes plus the dates their attributes change.

    The change dates are what make SCD2 possible: ``build_customer_extracts``
    replays them into periodic full extracts, exactly as a nightly dump of a
    mutable source table would.
    """
    ids = zero_padded_ids("CUS", block_start + 1, block_size)
    picks = rng.integers(0, len(identities), size=block_size)
    # Cast to a fixed-width string dtype: pandas hands back object arrays, which
    # the vectorised np.char routines below refuse to touch.
    first_names = identities["first_name"].to_numpy().astype(str)[picks]
    last_names = identities["last_name"].to_numpy().astype(str)[picks]

    # Sign-ups accelerate over the window -- a growing broker, so cohort charts
    # have a shape. beta(2, 1.2) is right-skewed towards recent dates.
    signup_offsets = (rng.beta(2.0, 1.2, size=block_size) * (config.days - 1)).astype(
        np.int64
    )
    created_dates = pd.to_datetime(config.start_date) + pd.to_timedelta(
        signup_offsets, unit="D"
    )

    countries = weighted_pick(rng, COUNTRIES, block_size)
    segments = weighted_pick(rng, [(s[0], s[1]) for s in SEGMENTS], block_size)

    numbers = np.char.zfill(
        np.arange(block_start + 1, block_start + block_size + 1).astype("U10"), 10
    )
    # Unique by construction -- the customer number in the local part is what
    # lets a 4,000-identity pool serve 150,000 customers without collisions.
    emails = (
        pd.Series(first_names).str.lower()
        + "."
        + pd.Series(last_names).str.lower().str.replace(r"[^a-z]", "", regex=True)
        + "+"
        + numbers
        + "@example.com"
    ).to_numpy()

    customers = pd.DataFrame(
        {
            "customer_id": ids,
            "first_name": first_names,
            "last_name": last_names,
            "email": emails,
            "phone_number": [
                f"+{c} {n[:3]} {n[3:6]} {n[6:]}"
                for c, n in zip(
                    rng.integers(1, 99, size=block_size).astype(str),
                    np.char.zfill(
                        rng.integers(100_000_000, 999_999_999, size=block_size).astype(
                            "U9"
                        ),
                        9,
                    ),
                    strict=True,
                )
            ],
            "date_of_birth": pd.to_datetime("1995-01-01")
            - pd.to_timedelta(rng.integers(-9_000, 9_000, size=block_size), unit="D"),
            "national_id": _fake_national_ids(rng, countries),
            "street_address": identities["street_address"].to_numpy()[picks],
            "city": identities["city"].to_numpy()[picks],
            "postcode": identities["postcode"].to_numpy()[picks],
            "country_code": countries,
            "created_at": created_dates,
            "segment": segments,
        }
    )

    # --- attribute drift -----------------------------------------------------
    # Each mutable attribute gets an optional single change, on a date after the
    # customer was created. This is the raw material for dim_customer's SCD2.
    horizon = np.clip(
        (pd.to_datetime(config.end_date) - created_dates).days.to_numpy(), 1, None
    )

    def change_date(probability: float, earliest_fraction: float = 0.05) -> pd.Series:
        occurs = rng.random(block_size) < probability
        offset = (
            earliest_fraction * horizon
            + rng.random(block_size) * (1 - earliest_fraction) * horizon
        ).astype(np.int64)
        dates = created_dates + pd.to_timedelta(offset, unit="D")
        return pd.Series(np.where(occurs, dates, pd.NaT), dtype="datetime64[ns]")

    # KYC almost always resolves, usually within a fortnight of sign-up.
    kyc_resolution_offset = rng.integers(1, 15, size=block_size)
    customers["kyc_resolved_at"] = created_dates + pd.to_timedelta(
        kyc_resolution_offset, unit="D"
    )
    resolution_roll = rng.random(block_size)
    customers["kyc_status_initial"] = "pending"
    customers["kyc_status_final"] = np.select(
        [resolution_roll < 0.94, resolution_roll < 0.98],
        ["verified", "review_required"],
        default="rejected",
    )

    customers["risk_rating_initial"] = weighted_pick(
        rng, [("low", 55), ("medium", 33), ("high", 12)], block_size
    )
    customers["risk_rating_final"] = weighted_pick(
        rng, [("low", 40), ("medium", 40), ("high", 20)], block_size
    )
    customers["risk_changed_at"] = change_date(0.22)

    customers["tier_initial"] = "bronze"
    customers["tier_final"] = weighted_pick(
        rng,
        [(t, w) for t, w in zip(CUSTOMER_TIERS, [10, 45, 32, 13], strict=True)],
        block_size,
    )
    customers["tier_changed_at"] = change_date(0.35)

    customers["marketing_opt_in_initial"] = rng.random(block_size) < 0.62
    customers["marketing_opt_in_final"] = ~customers["marketing_opt_in_initial"]
    customers["marketing_changed_at"] = change_date(0.18)

    # Email and address changes are the cases the masking framework most needs
    # to survive: the PII value itself is versioned.
    customers["email_final"] = np.char.replace(
        customers["email"].to_numpy().astype(str), "@example.com", "@example.net"
    )
    customers["email_changed_at"] = change_date(0.08)

    customers["street_address_final"] = np.char.add(
        "Unit ",
        np.char.add(
            rng.integers(1, 99, size=block_size).astype(str),
            np.char.add("/", customers["street_address"].to_numpy().astype(str)),
        ),
    )
    customers["address_changed_at"] = change_date(0.14)

    return customers


def _fake_national_ids(rng: np.random.Generator, countries: np.ndarray) -> np.ndarray:
    """Fake national IDs shaped like the real formats, per country.

    Shape matters: a classification framework that can only recognise PII by
    column name is not much of a framework, and these give a regex-based
    detector something honest to chew on.
    """
    formats = dict((code, fmt) for code, fmt, _ in COUNTRIES)
    letters = np.array(list("ABCDEFGHJKLMNPQRSTUVWXYZ"))
    out = np.empty(len(countries), dtype=object)
    for code, template in formats.items():
        mask = countries == code
        count = int(mask.sum())
        if not count:
            continue
        digits = rng.integers(0, 10, size=(count, template.count("#"))).astype(str)
        alphas = rng.choice(letters, size=(count, template.count("@")))
        values = []
        for row_digits, row_alphas in zip(digits, alphas, strict=True):
            digit_iter, alpha_iter = iter(row_digits), iter(row_alphas)
            values.append(
                "".join(
                    next(digit_iter)
                    if char == "#"
                    else next(alpha_iter)
                    if char == "@"
                    else char
                    for char in template
                )
            )
        out[mask] = values
    return out


def build_customer_extracts(
    config: Config, customers: pd.DataFrame, extract_dates: pd.DatetimeIndex
) -> pd.DataFrame:
    """Replay attribute drift into periodic full-table extracts.

    One row per customer per extract date, containing that customer's state as
    at that date -- the shape of a nightly full dump of a mutable OLTP table.
    ``dim_customer`` reconstructs SCD2 from these, which is why the whole SCD2
    story is reproducible in a single dbt run instead of needing weeks of
    accumulated snapshots. See docs/adr/0004.
    """
    frames = []
    for extract_date in extract_dates:
        live = customers[customers["created_at"] <= extract_date]
        if live.empty:
            continue

        def as_of(base: str, final: str, changed: str, source=live, when=extract_date):
            changed_at = source[changed]
            return np.where(
                changed_at.notna() & (changed_at <= when), source[final], source[base]
            )

        kyc_resolved = live["kyc_resolved_at"] <= extract_date
        frames.append(
            pd.DataFrame(
                {
                    "customer_id": live["customer_id"].to_numpy(),
                    "first_name": live["first_name"].to_numpy(),
                    "last_name": live["last_name"].to_numpy(),
                    "email": as_of("email", "email_final", "email_changed_at"),
                    "phone_number": live["phone_number"].to_numpy(),
                    "date_of_birth": live["date_of_birth"].to_numpy(),
                    "national_id": live["national_id"].to_numpy(),
                    "street_address": as_of(
                        "street_address", "street_address_final", "address_changed_at"
                    ),
                    "city": live["city"].to_numpy(),
                    "postcode": live["postcode"].to_numpy(),
                    "country_code": live["country_code"].to_numpy(),
                    "kyc_status": np.where(
                        kyc_resolved,
                        live["kyc_status_final"],
                        live["kyc_status_initial"],
                    ),
                    "risk_rating": as_of(
                        "risk_rating_initial", "risk_rating_final", "risk_changed_at"
                    ),
                    "customer_tier": as_of(
                        "tier_initial", "tier_final", "tier_changed_at"
                    ),
                    "marketing_opt_in": as_of(
                        "marketing_opt_in_initial",
                        "marketing_opt_in_final",
                        "marketing_changed_at",
                    ).astype(bool),
                    "created_at": live["created_at"].to_numpy(),
                    "extract_date": extract_date.date().isoformat(),
                }
            )
        )

    extracts = pd.concat(frames, ignore_index=True)
    # updated_at is the most recent change that had happened by the extract
    # date. Sourced from the extract itself so it stays internally consistent.
    change_columns = [
        "risk_changed_at",
        "tier_changed_at",
        "marketing_changed_at",
        "email_changed_at",
        "address_changed_at",
        "kyc_resolved_at",
    ]
    change_lookup = customers.set_index("customer_id")[change_columns]
    joined = extracts.join(change_lookup, on="customer_id")
    extract_ts = pd.to_datetime(extracts["extract_date"])
    applied = joined[change_columns].where(joined[change_columns].le(extract_ts, axis=0))
    extracts["updated_at"] = applied.max(axis=1).fillna(extracts["created_at"])
    extracts["ingested_at"] = pd.Timestamp.now(tz=UTC)
    return extracts


def build_accounts(
    rng: np.random.Generator, config: Config, customers: pd.DataFrame, id_offset: int
) -> pd.DataFrame:
    """One to three accounts per customer, opened on or after sign-up."""
    counts = rng.choice([1, 2, 3], size=len(customers), p=[0.68, 0.26, 0.06])
    total = int(counts.sum())
    owner = np.repeat(np.arange(len(customers)), counts)

    opened_offset = rng.integers(0, 30, size=total)
    opened_at = customers["created_at"].to_numpy()[owner] + pd.to_timedelta(
        opened_offset, unit="D"
    )
    opened_at = np.minimum(opened_at, np.datetime64(config.end_date))

    # A small share of accounts close during the window, which the SCD1 account
    # dimension and the daily snapshot facts both have to handle.
    closes = rng.random(total) < 0.04
    close_offset = rng.integers(30, 400, size=total)
    closed_at = np.where(
        closes,
        opened_at + pd.to_timedelta(close_offset, unit="D"),
        np.datetime64("NaT"),
    )
    closed_at = np.where(
        pd.isna(closed_at) | (closed_at > np.datetime64(config.end_date)),
        np.datetime64("NaT"),
        closed_at,
    )

    base_currency = np.where(
        customers["country_code"].to_numpy()[owner] == "AU",
        "AUD",
        np.where(
            np.isin(customers["country_code"].to_numpy()[owner], ["DE", "NL"]),
            "EUR",
            np.where(customers["country_code"].to_numpy()[owner] == "GB", "GBP", "USD"),
        ),
    )

    return pd.DataFrame(
        {
            "account_id": zero_padded_ids("ACC", id_offset + 1, total),
            "customer_id": customers["customer_id"].to_numpy()[owner],
            "account_type": weighted_pick(rng, ACCOUNT_TYPES, total),
            "base_currency": base_currency,
            "opened_at": opened_at,
            "closed_at": pd.to_datetime(closed_at),
            "account_status": np.where(pd.isna(closed_at), "open", "closed"),
            "segment": customers["segment"].to_numpy()[owner],
            "margin_limit": np.round(rng.lognormal(9.5, 1.0, size=total), 2),
            "ingested_at": pd.Timestamp.now(tz=UTC),
        }
    )


# --------------------------------------------------------------------------- #
# Trading activity
# --------------------------------------------------------------------------- #


def build_orders(
    rng: np.random.Generator,
    config: Config,
    accounts: pd.DataFrame,
    instruments: pd.DataFrame,
    calendar: pd.DataFrame,
    close_prices: np.ndarray,
    id_offset: int,
) -> pd.DataFrame:
    """One row per order, at its terminal state.

    Order counts come from a Poisson draw over each account's active window
    rather than a per-account-per-day matrix, so cost is proportional to the
    number of orders instead of ``accounts x days``. That is the difference
    between the ``large`` preset running in a minute and not running at all.
    """
    segment_rates = dict((name, rate) for name, _, rate, _ in SEGMENTS)
    segment_notionals = dict((name, notional) for name, _, _, notional in SEGMENTS)

    calendar_dates = calendar["calendar_date"].to_numpy()
    n_days = len(calendar)
    opened_index = (
        (accounts["opened_at"].to_numpy() - np.datetime64(config.start_date))
        .astype("timedelta64[D]")
        .astype(np.int64)
    )
    opened_index = np.clip(opened_index, 0, n_days - 1)
    closed_index = np.where(
        accounts["closed_at"].notna(),
        (
            (
                accounts["closed_at"].fillna(pd.Timestamp(config.end_date)).to_numpy()
                - np.datetime64(config.start_date)
            )
            .astype("timedelta64[D]")
            .astype(np.int64)
        ),
        n_days - 1,
    )
    closed_index = np.clip(closed_index, opened_index, n_days - 1)
    active_days = (closed_index - opened_index + 1).astype(np.int64)

    rates = np.array([segment_rates[s] for s in accounts["segment"]])
    order_counts = rng.poisson(rates * active_days)
    total_orders = int(order_counts.sum())
    if total_orders == 0:
        return pd.DataFrame()

    account_axis = np.repeat(np.arange(len(accounts)), order_counts)
    # Uniform within each account's active window.
    day_offsets = (
        rng.random(total_orders) * np.repeat(active_days, order_counts)
    ).astype(np.int64)
    raw_day_index = np.repeat(opened_index, order_counts) + day_offsets
    raw_day_index = np.clip(raw_day_index, 0, n_days - 1)

    instrument_axis = rng.choice(
        len(instruments),
        size=total_orders,
        p=instruments["popularity"].to_numpy() / instruments["popularity"].sum(),
    )
    is_crypto = (instruments["asset_class"] == "crypto").to_numpy()[instrument_axis]

    # Orders placed while the market is shut roll into the next session.
    session_index = calendar["next_session_index"].to_numpy()[raw_day_index]
    day_index = np.where(is_crypto, raw_day_index, session_index)

    # A closed day at the very end of the window has no next session to roll
    # into, so build_calendar falls back to the previous one -- which can land an
    # order *before* its own account was opened. An order placed on the final
    # Saturday of the window genuinely has not resolved yet, so it is dropped
    # rather than back-dated. Small in number, and the alternative is fills that
    # predate the account they belong to.
    account_opened_index = np.repeat(opened_index, order_counts)
    within_account_life = day_index >= account_opened_index
    if not within_account_life.all():
        account_axis = account_axis[within_account_life]
        instrument_axis = instrument_axis[within_account_life]
        day_index = day_index[within_account_life]
        is_crypto = is_crypto[within_account_life]
        total_orders = int(within_account_life.sum())
        if total_orders == 0:
            return pd.DataFrame()

    reference_price = close_prices[instrument_axis, day_index]
    notional_means = np.array(
        [segment_notionals[s] for s in accounts["segment"].to_numpy()[account_axis]]
    )
    target_notional = notional_means * rng.lognormal(
        0.0, NOTIONAL_SIGMA, size=total_orders
    )
    raw_quantity = target_notional / reference_price
    # Equities and ETFs trade in whole units; crypto is fractional to 6 dp,
    # which is exactly the case that punishes anyone storing quantity as an int.
    quantity = np.where(
        is_crypto,
        np.round(np.maximum(raw_quantity, 0.000001), 6),
        np.maximum(np.round(raw_quantity), 1.0),
    )

    order_types = weighted_pick(rng, ORDER_TYPES, total_orders)
    sides = rng.choice(
        ["buy", "sell"],
        size=total_orders,
        p=[BUY_PROBABILITY, 1 - BUY_PROBABILITY],
    )

    # Limit and stop orders cancel far more often than market orders, so the
    # status draw is conditioned on order type rather than drawn once globally.
    status = np.empty(total_orders, dtype=object)
    base_statuses = [s for s, _ in ORDER_STATUSES]
    base_weights = np.array([w for _, w in ORDER_STATUSES], dtype=float)
    for order_type in {"market", "limit", "stop", "stop_limit"}:
        mask = order_types == order_type
        count = int(mask.sum())
        if not count:
            continue
        weights = base_weights.copy()
        if order_type != "market":
            weights = weights * np.array([0.72, 1.6, 2.6, 1.2])
        status[mask] = rng.choice(base_statuses, size=count, p=weights / weights.sum())

    limit_price = np.where(
        np.isin(order_types, ["limit", "stop", "stop_limit"]),
        np.round(reference_price * (1.0 + rng.normal(0.0, 0.02, total_orders)), 4),
        np.nan,
    )

    session_open = np.timedelta64(9 * 3600 + 30 * 60, "s")
    session_span = 6 * 3600 + 30 * 60
    intraday = np.where(
        is_crypto,
        (rng.random(total_orders) * 86_399).astype(np.int64),
        (
            session_open.astype(np.int64)
            + u_shaped_seconds(rng, total_orders, session_span)
        ),
    )
    placed_at = calendar_dates[day_index] + intraday.astype("timedelta64[s]")

    # Terminal timestamp: fills resolve fast, cancels linger.
    resolution_seconds = np.where(
        np.isin(status, ["filled", "partially_filled"]),
        rng.integers(1, 900, size=total_orders),
        rng.integers(60, 40_000, size=total_orders),
    )
    resolved_at = placed_at + resolution_seconds.astype("timedelta64[s]")

    orders = pd.DataFrame(
        {
            "order_id": zero_padded_ids("ORD", id_offset + 1, total_orders),
            "account_id": accounts["account_id"].to_numpy()[account_axis],
            "instrument_id": instruments["instrument_id"].to_numpy()[instrument_axis],
            "side": sides,
            "order_type": order_types,
            "quantity": quantity,
            "limit_price": limit_price,
            "order_status": status.astype(str),
            "placed_at": placed_at,
            "resolved_at": resolved_at,
            "channel": weighted_pick(rng, CHANNELS, total_orders),
            "time_in_force": rng.choice(
                ["day", "gtc", "ioc"], size=total_orders, p=[0.7, 0.27, 0.03]
            ),
            "ingested_at": pd.Timestamp.now(tz=UTC),
        }
    )
    orders["placed_date"] = pd.to_datetime(orders["placed_at"]).dt.date.astype(str)
    # Carried for the execution builder, dropped before writing.
    orders["_day_index"] = day_index
    orders["_instrument_axis"] = instrument_axis
    return orders


def build_executions(
    rng: np.random.Generator,
    orders: pd.DataFrame,
    instruments: pd.DataFrame,
    prices: pd.DataFrame,
    id_offset: int,
) -> pd.DataFrame:
    """One row per fill. Many-to-one against orders, and zero for cancels.

    Fill prices are drawn inside the day's actual high/low band rather than at
    the close, so slippage analysis has something real to measure.
    """
    fillable = orders[orders["order_status"].isin(["filled", "partially_filled"])]
    if fillable.empty:
        return pd.DataFrame()

    n = len(fillable)
    is_crypto = (instruments["asset_class"] == "crypto").to_numpy()[
        fillable["_instrument_axis"].to_numpy()
    ]

    # Fully filled orders deliver their whole quantity; partial fills deliver
    # 20-80% of it. Crypto fills in one hit, equities can fragment.
    fill_fraction = np.where(
        fillable["order_status"].to_numpy() == "filled",
        1.0,
        rng.uniform(0.2, 0.8, size=n),
    )
    filled_quantity = fillable["quantity"].to_numpy() * fill_fraction

    # Whole-unit instruments split into whole-unit fills; fractional ones don't
    # split at all, which keeps split_quantity working on integers.
    #
    # The floor is clamped to 1. A one-share order that partially fills would
    # otherwise floor to zero quantity, and a zero-quantity fill is not a
    # partial fill -- it is a fill that did not happen. It also breaks
    # split_quantity, which assumes every piece can carry at least one unit.
    integer_quantity = np.where(
        is_crypto, 1.0, np.maximum(np.floor(filled_quantity), 1.0)
    )
    max_parts = np.where(is_crypto, 1, np.minimum(3, integer_quantity))
    parts = np.maximum(
        1,
        np.minimum(max_parts, rng.choice([1, 2, 3], size=n, p=[0.72, 0.21, 0.07])),
    ).astype(np.int64)

    group_index, pieces = split_quantity(rng, integer_quantity, parts)
    # Restore fractional quantities for crypto: a single piece carrying the lot,
    # floored at the smallest unit the source system records.
    crypto_rows = is_crypto[group_index]
    pieces = np.where(
        crypto_rows,
        np.maximum(np.round(filled_quantity[group_index], 6), 0.000001),
        pieces,
    )

    total_fills = len(group_index)
    source = fillable.iloc[group_index]

    # Price inside the day's traded range.
    price_lookup = prices.set_index(["instrument_id", "price_date"])
    keys = pd.MultiIndex.from_arrays(
        [
            source["instrument_id"].to_numpy(),
            pd.to_datetime(source["placed_date"]).to_numpy(),
        ]
    )
    day_prices = price_lookup.reindex(keys)
    low = day_prices["low_price"].to_numpy()
    high = day_prices["high_price"].to_numpy()
    close = day_prices["close_price"].to_numpy()
    # Orders that rolled into the next session have no price row for their
    # placed_date; fall back to the close the order was sized against.
    band_missing = np.isnan(low) | np.isnan(high)
    low = np.where(band_missing, close, low)
    high = np.where(band_missing, close, high)
    fill_price = np.where(
        np.isnan(low),
        1.0,
        low + rng.random(total_fills) * np.maximum(high - low, 0.0),
    )
    fill_price = np.round(fill_price, 4)

    currency = instruments["currency"].to_numpy()[source["_instrument_axis"].to_numpy()]
    asset_class = instruments["asset_class"].to_numpy()[
        source["_instrument_axis"].to_numpy()
    ]

    # Commission-free US equities, flat fee offshore, percentage on crypto.
    notional = pieces * fill_price
    commission = np.select(
        [asset_class == "crypto", currency != REPORTING_CURRENCY],
        [np.round(notional * 0.001, 4), 0.99],
        default=0.0,
    )

    executed_at = pd.to_datetime(source["placed_at"].to_numpy()) + pd.to_timedelta(
        rng.integers(1, 600, size=total_fills), unit="s"
    )

    executions = pd.DataFrame(
        {
            "execution_id": zero_padded_ids("EXE", id_offset + 1, total_fills),
            "order_id": source["order_id"].to_numpy(),
            "quantity": pieces,
            "execution_price": fill_price,
            "currency": currency,
            "commission": commission,
            "venue": weighted_pick(rng, VENUES, total_fills),
            "executed_at": executed_at,
            "ingested_at": pd.Timestamp.now(tz=UTC),
        }
    )
    executions["executed_date"] = executions["executed_at"].dt.date.astype(str)
    return executions


def build_cash_movements(
    rng: np.random.Generator,
    config: Config,
    accounts: pd.DataFrame,
    executions: pd.DataFrame,
    instruments: pd.DataFrame,
    id_offset: int,
) -> pd.DataFrame:
    """Deposits, withdrawals, fees, interest and dividends.

    Dividends are approximated from buy-side fills of dividend-paying
    instruments rather than from a true position ledger -- a deliberate
    simplification, since reconstructing holdings here would duplicate the
    warehouse's own job. It is documented as an approximation because the
    ``fct_account_daily`` cash column depends on it.
    """
    frames = []
    n_accounts = len(accounts)
    end = pd.Timestamp(config.end_date)

    active_days = (
        (accounts["closed_at"].fillna(end).to_numpy() - accounts["opened_at"].to_numpy())
        .astype("timedelta64[D]")
        .astype(np.int64)
        .clip(1)
    )

    # --- how much this account will need ------------------------------------
    # Funding is derived from trading appetite rather than drawn from a fixed
    # distribution. A whale placing $24,000 orders daily and depositing $3,000 a
    # month ends the window hundreds of thousands of dollars overdrawn -- which
    # is arithmetically inevitable, impossible on a cash account, and turns
    # every balance-sheet measure in the warehouse into nonsense.
    #
    # Buys exceed sells, so an account accumulates holdings at
    # orders/day x notional x (2p - 1). Funding it to that level plus a buffer
    # keeps cash balances positive without simulating each order against a
    # running balance.
    segment_rates = dict((name, rate) for name, _, rate, _ in SEGMENTS)
    segment_notionals = dict((name, notional) for name, _, _, notional in SEGMENTS)
    order_rate = np.array([segment_rates[s] for s in accounts["segment"]])
    order_notional = np.array([segment_notionals[s] for s in accounts["segment"]])
    expected_net_invested = (
        order_rate
        * order_notional
        * NOTIONAL_MEAN_FACTOR
        * (2 * BUY_PROBABILITY - 1)
        * active_days
    )
    funding_need = expected_net_invested * FUNDING_BUFFER

    # --- opening deposit, one per account ------------------------------------
    # Front-loaded: funding has to lead spending, not lag it. Splitting evenly
    # across the account's life leaves the early months overdrawn even when the
    # lifetime total is ample.
    opening_amount = np.round(
        np.maximum(
            funding_need * 0.75 * rng.lognormal(0.0, 0.25, size=n_accounts), 500.0
        ),
        2,
    )
    frames.append(
        pd.DataFrame(
            {
                "account_id": accounts["account_id"].to_numpy(),
                "movement_type": "deposit",
                "amount": opening_amount,
                "currency": accounts["base_currency"].to_numpy(),
                "occurred_at": accounts["opened_at"].to_numpy(),
                "payment_method": weighted_pick(rng, PAYMENT_METHODS, n_accounts),
            }
        )
    )

    # --- recurring deposits and withdrawals ----------------------------------
    monthly_funding = funding_need * 0.25 / np.maximum(active_days / 30.0, 1.0)
    for movement_type, monthly_rate, scale, sign in (
        ("deposit", 0.9, 1.0, 1),
        ("withdrawal", 0.25, 0.35, -1),
    ):
        counts = rng.poisson(monthly_rate * active_days / 30.0)
        total = int(counts.sum())
        if not total:
            continue
        axis = np.repeat(np.arange(n_accounts), counts)
        # Skewed towards the start of the account's life for the same reason the
        # opening deposit is front-loaded: money has to be there before it is
        # spent. beta(1.5, 2.5) puts the mass in the first third.
        offset = (rng.beta(1.5, 2.5, size=total) * np.repeat(active_days, counts)).astype(
            np.int64
        )
        # Each instalment is sized so the expected sum over the account's life
        # delivers the remaining funding need.
        per_instalment = monthly_funding[axis] * scale / monthly_rate
        frames.append(
            pd.DataFrame(
                {
                    "account_id": accounts["account_id"].to_numpy()[axis],
                    "movement_type": movement_type,
                    "amount": sign
                    * np.round(
                        np.maximum(
                            per_instalment * rng.lognormal(0.0, 0.5, size=total), 20.0
                        ),
                        2,
                    ),
                    "currency": accounts["base_currency"].to_numpy()[axis],
                    "occurred_at": accounts["opened_at"].to_numpy()[axis]
                    + pd.to_timedelta(offset, unit="D"),
                    "payment_method": weighted_pick(rng, PAYMENT_METHODS, total),
                }
            )
        )

    # --- monthly platform fee on margin accounts -----------------------------
    margin = accounts[accounts["account_type"] == "margin"]
    if not margin.empty:
        months = (
            (margin["closed_at"].fillna(end).to_numpy() - margin["opened_at"].to_numpy())
            .astype("timedelta64[D]")
            .astype(np.int64)
            // 30
        ).clip(0)
        total = int(months.sum())
        if total:
            axis = np.repeat(np.arange(len(margin)), months)
            month_number = np.concatenate([np.arange(m) for m in months if m > 0])
            frames.append(
                pd.DataFrame(
                    {
                        "account_id": margin["account_id"].to_numpy()[axis],
                        "movement_type": "fee",
                        "amount": -10.0,
                        "currency": margin["base_currency"].to_numpy()[axis],
                        "occurred_at": margin["opened_at"].to_numpy()[axis]
                        + pd.to_timedelta((month_number + 1) * 30, unit="D"),
                        "payment_method": "direct_debit",
                    }
                )
            )

    # --- dividends, approximated from buy fills ------------------------------
    if not executions.empty:
        yields = dict(
            zip(
                instruments["instrument_id"],
                instruments["dividend_yield"],
                strict=True,
            )
        )
        sampled = executions.sample(frac=0.08, random_state=int(rng.integers(0, 2**31)))
        if not sampled.empty:
            frames.append(
                pd.DataFrame(
                    {
                        "account_id": sampled["_account_id"].to_numpy(),
                        "movement_type": "dividend",
                        "amount": np.round(
                            sampled["quantity"].to_numpy()
                            * sampled["execution_price"].to_numpy()
                            * np.array(
                                [yields.get(i, 0.0) for i in sampled["_instrument_id"]]
                            )
                            / 4.0,
                            2,
                        ),
                        "currency": sampled["currency"].to_numpy(),
                        "occurred_at": sampled["executed_at"].to_numpy()
                        + pd.to_timedelta(
                            rng.integers(30, 95, size=len(sampled)), unit="D"
                        ),
                        "payment_method": "bank_transfer",
                    }
                )
            )

    movements = pd.concat(frames, ignore_index=True)
    movements = movements[movements["occurred_at"] <= end]
    movements = movements[movements["amount"].abs() > 0.009].reset_index(drop=True)
    movements.insert(
        0, "movement_id", zero_padded_ids("CSH", id_offset + 1, len(movements))
    )
    movements["occurred_date"] = pd.to_datetime(movements["occurred_at"]).dt.date.astype(
        str
    )
    movements["ingested_at"] = pd.Timestamp.now(tz=UTC)
    return movements


def build_app_events(
    rng: np.random.Generator,
    config: Config,
    customers: pd.DataFrame,
    id_offset: int,
) -> pd.DataFrame:
    """Clickstream sessions. The largest table, as event data always is.

    Carries ``ip_address`` and ``user_agent`` -- the columns most often missed
    by a classification exercise that only looks for obvious identity fields.
    """
    n_customers = len(customers)
    end = pd.Timestamp(config.end_date)
    active_days = (end - customers["created_at"]).dt.days.clip(lower=1).to_numpy()
    engagement = np.array(
        [SEGMENT_ENGAGEMENT[s] for s in customers["segment"]], dtype=float
    )
    session_counts = rng.poisson(engagement * active_days)
    total_sessions = int(session_counts.sum())
    if total_sessions == 0:
        return pd.DataFrame()

    customer_axis = np.repeat(np.arange(n_customers), session_counts)
    day_offset = (
        rng.random(total_sessions) * np.repeat(active_days, session_counts)
    ).astype(np.int64)
    session_start = (
        customers["created_at"].to_numpy()[customer_axis]
        + pd.to_timedelta(day_offset, unit="D")
        + pd.to_timedelta(rng.integers(0, 86_400, size=total_sessions), unit="s")
    )

    events_per_session = rng.integers(2, 7, size=total_sessions)
    total_events = int(events_per_session.sum())
    session_axis = np.repeat(np.arange(total_sessions), events_per_session)

    # Each customer keeps one to three sticky IPs and one device family, so
    # device and network attributes are consistent per user rather than random
    # noise -- which is what makes them useful (and identifying).
    customer_ips = to_ip_addresses(rng, n_customers)
    device_index = weighted_pick(
        rng, [(i, d[-1]) for i, d in enumerate(DEVICE_FAMILIES)], n_customers
    ).astype(int)

    within_session = rng.integers(5, 900, size=total_events).cumsum()
    session_offsets = np.concatenate(
        ([0], within_session[np.cumsum(events_per_session)[:-1] - 1])
    )
    occurred_at = pd.to_datetime(session_start[session_axis]) + pd.to_timedelta(
        within_session - session_offsets[session_axis], unit="s"
    )

    device_axis = device_index[customer_axis[session_axis]]
    # Built as categoricals from integer codes rather than by fancy-indexing an
    # array of strings. Indexing would materialise one full copy of a ~120
    # character user-agent per event -- 1.2 GB of fixed-width numpy at this
    # scale, for six distinct values. from_codes keeps it to the codes plus a
    # six-element dictionary.
    events = pd.DataFrame(
        {
            "event_id": zero_padded_ids("EVT", id_offset + 1, total_events),
            "session_id": np.char.add(
                "SES-",
                np.char.zfill((session_axis + id_offset + 1).astype("U12"), 12),
            ),
            "customer_id": customers["customer_id"].to_numpy()[
                customer_axis[session_axis]
            ],
            "event_type": pd.Categorical(
                weighted_pick(rng, APP_EVENT_TYPES, total_events)
            ),
            "occurred_at": occurred_at,
            "device_family": pd.Categorical.from_codes(
                device_axis, categories=[d[0] for d in DEVICE_FAMILIES]
            ),
            "user_agent": pd.Categorical.from_codes(
                device_axis, categories=[d[1] for d in DEVICE_FAMILIES]
            ),
            "ip_address": customer_ips[customer_axis[session_axis]],
            "app_version": pd.Categorical(
                rng.choice(
                    ["4.2.1", "4.2.0", "4.1.3", "3.9.8"],
                    size=total_events,
                    p=[0.55, 0.24, 0.15, 0.06],
                )
            ),
            "ingested_at": pd.Timestamp.now(tz=UTC),
        }
    )
    events = events[events["occurred_at"] <= end].reset_index(drop=True)
    events["event_date"] = events["occurred_at"].dt.date.astype(str)
    return events


# --------------------------------------------------------------------------- #
# Anomaly injection
# --------------------------------------------------------------------------- #


def inject_anomalies(
    rng: np.random.Generator,
    orders: pd.DataFrame,
    executions: pd.DataFrame,
    extracts: pd.DataFrame,
    stats: Stats,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Plant defects the data quality suite is expected to catch.

    Each defect maps to a named test in ``warehouse/tests/``. Running
    ``make demo-anomalies`` should turn those tests red and fire the Slack
    alert -- the only honest way to show that the checks work.
    """
    counts: dict[str, int] = {}

    if not executions.empty:
        # 1. Duplicate fills -- the classic idempotency failure in ingestion.
        duplicates = executions.sample(
            n=max(1, len(executions) // 500),
            random_state=int(rng.integers(0, 2**31)),
        )
        executions = pd.concat([executions, duplicates], ignore_index=True)
        counts["duplicate_executions"] = len(duplicates)

        # 2. Over-fills: more quantity delivered than the order asked for.
        over_filled = executions.sample(
            n=max(1, len(executions) // 1000),
            random_state=int(rng.integers(0, 2**31)),
        ).index
        executions.loc[over_filled, "quantity"] *= 3.0
        counts["over_filled_orders"] = len(over_filled)

        # 3. Fills timestamped before their order existed.
        back_dated = executions.sample(
            n=max(1, len(executions) // 2000),
            random_state=int(rng.integers(0, 2**31)),
        ).index
        executions.loc[back_dated, "executed_at"] -= pd.Timedelta(days=3)
        counts["executions_before_order"] = len(back_dated)

    if not orders.empty:
        # 4. Orphan orders pointing at an account that does not exist.
        orphans = orders.sample(
            n=max(1, len(orders) // 1000),
            random_state=int(rng.integers(0, 2**31)),
        ).index
        orders.loc[orphans, "account_id"] = "ACC-9999999999"
        counts["orphan_orders"] = len(orphans)

        # 5. Negative quantities, which should never reach the warehouse.
        negatives = orders.sample(
            n=max(1, len(orders) // 2000),
            random_state=int(rng.integers(0, 2**31)),
        ).index
        orders.loc[negatives, "quantity"] *= -1
        counts["negative_quantities"] = len(negatives)

    if not extracts.empty:
        # 6. Missing PII -- a not_null violation on a classified column.
        blanked = extracts.sample(
            n=max(1, len(extracts) // 2000),
            random_state=int(rng.integers(0, 2**31)),
        ).index
        extracts.loc[blanked, "email"] = None
        counts["null_emails"] = len(blanked)

    stats.anomalies = counts
    return orders, executions, extracts


# --------------------------------------------------------------------------- #
# Orchestration of the generation run
# --------------------------------------------------------------------------- #


def extract_dates_for(config: Config) -> pd.DatetimeIndex:
    """Month-end customer extract dates, plus the final day of the window.

    Monthly cadence keeps the extract table small while still giving SCD2
    several versions per customer to reconstruct.
    """
    dates = pd.date_range(config.start_date, config.end_date, freq="ME")
    final = pd.Timestamp(config.end_date)
    if len(dates) == 0 or dates[-1] != final:
        dates = dates.append(pd.DatetimeIndex([final]))
    return dates


def generate(config: Config) -> Stats:
    started = time.perf_counter()
    stats = Stats()

    if config.out_dir.exists():
        shutil.rmtree(config.out_dir)
    config.out_dir.mkdir(parents=True, exist_ok=True)

    zone = LandingZone(config.out_dir, stats)
    global_rng = np.random.default_rng(config.seed)

    calendar = build_calendar(config)
    instruments = build_instruments(global_rng)
    prices, close_prices = build_market_prices(global_rng, instruments, calendar)
    fx_rates = build_fx_rates(global_rng, calendar)

    zone.write("instruments", instruments.drop(columns=["popularity"]))
    zone.write("market_prices", prices)
    zone.write("fx_rates", fx_rates)

    identities = build_identity_pool(config.seed)
    extract_dates = extract_dates_for(config)

    account_offset = 0
    order_offset = 0
    execution_offset = 0
    movement_offset = 0
    event_offset = 0

    n_blocks = (config.customers + CUSTOMER_BLOCK_SIZE - 1) // CUSTOMER_BLOCK_SIZE
    for block in range(n_blocks):
        block_start = block * CUSTOMER_BLOCK_SIZE
        block_size = min(CUSTOMER_BLOCK_SIZE, config.customers - block_start)
        # Seeded per block: reproducible, and independent of block ordering.
        rng = np.random.default_rng([config.seed, block])
        if n_blocks > 1:
            print(
                f"  block {block + 1}/{n_blocks} ({block_size:,} customers)...",
                flush=True,
            )

        customers = build_customers(rng, config, identities, block_start, block_size)
        extracts = build_customer_extracts(config, customers, extract_dates)
        accounts = build_accounts(rng, config, customers, account_offset)
        orders = build_orders(
            rng,
            config,
            accounts,
            instruments,
            calendar,
            close_prices,
            order_offset,
        )

        executions = pd.DataFrame()
        if not orders.empty:
            executions = build_executions(
                rng, orders, instruments, prices, execution_offset
            )

        # Cash movements need the account and instrument behind each fill;
        # attach them as private columns rather than re-joining downstream.
        if not executions.empty:
            order_lookup = orders.set_index("order_id")[["account_id", "instrument_id"]]
            joined = executions.join(order_lookup, on="order_id")
            executions["_account_id"] = joined["account_id"].to_numpy()
            executions["_instrument_id"] = joined["instrument_id"].to_numpy()

        movements = build_cash_movements(
            rng, config, accounts, executions, instruments, movement_offset
        )

        events = pd.DataFrame()
        if config.include_events:
            events = build_app_events(rng, config, customers, event_offset)

        if config.inject_anomalies:
            orders, executions, extracts = inject_anomalies(
                rng, orders, executions, extracts, stats
            )

        zone.write("customer_extracts", extracts)
        zone.write("accounts", accounts.drop(columns=["segment"]))
        if not orders.empty:
            zone.write("orders", orders.drop(columns=["_day_index", "_instrument_axis"]))
        if not executions.empty:
            zone.write(
                "executions",
                executions.drop(columns=["_account_id", "_instrument_id"]),
            )
        zone.write("cash_movements", movements)
        if not events.empty:
            zone.write("app_events", events)

        account_offset += len(accounts)
        order_offset += len(orders)
        execution_offset += len(executions)
        movement_offset += len(movements)
        event_offset += len(events)

    stats.elapsed_seconds = round(time.perf_counter() - started, 2)
    write_manifest(config, stats)
    return stats


def write_manifest(config: Config, stats: Stats) -> None:
    """Record what was generated, next to the data.

    Read by the freshness tests, the data quality dashboard page and the
    Dagster asset metadata, so provenance travels with the files.
    """
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "generator_version": "0.1.0",
        "scale": config.scale_name,
        "seed": config.seed,
        "customers": config.customers,
        "days": config.days,
        "start_date": config.start_date.isoformat(),
        "end_date": config.end_date.isoformat(),
        "include_events": config.include_events,
        "anomalies_injected": config.inject_anomalies,
        "anomaly_counts": stats.anomalies,
        "row_counts": stats.rows,
        "total_rows": sum(stats.rows.values()),
        "elapsed_seconds": stats.elapsed_seconds,
    }
    (config.out_dir / "_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def parse_args(argv: list[str] | None = None) -> Config:
    parser = argparse.ArgumentParser(
        description="Generate the tradeflow synthetic landing zone.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--scale",
        choices=sorted(SCALE_PRESETS),
        default="small",
        help="Row-count preset. Overridden by --customers/--days.",
    )
    parser.add_argument("--customers", type=int, help="Override the customer count.")
    parser.add_argument("--days", type=int, help="Override the history length in days.")
    parser.add_argument(
        "--seed", type=int, default=42, help="Seed for reproducible output."
    )
    parser.add_argument(
        "--end-date",
        type=lambda s: date.fromisoformat(s),
        # Yesterday in UTC. Two things are load-bearing here, and both were bugs.
        #
        # *Yesterday, not today.* A nightly batch lands the previous day's data,
        # which is the realistic shape -- and ending today produces order timestamps
        # later than the wall clock, because intraday times are drawn across a whole
        # session regardless of the hour it currently is. `int_orders_screened`
        # then correctly quarantines them as `placed_in_future`, their executions
        # cascade to `orphan_order`, and a clean run fails its own quality gate.
        #
        # *UTC, not local.* The warehouse runs its session in UTC and compares
        # against CURRENT_TIMESTAMP, so a local `date.today()` is a day ahead for
        # anyone east of Greenwich. Crypto draws intraday times across a full 24
        # hours, so those orders landed in the future even after the first fix.
        # Ending on UTC yesterday means every timestamp is provably in the past,
        # whatever timezone the machine is in -- and it stays deterministic, which
        # clamping to "now" would not.
        default=datetime.now(UTC).date() - timedelta(days=1),
        help="Last day of generated history (ISO format). Defaults to yesterday.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/landing"),
        help="Landing zone root. Wiped before each run.",
    )
    parser.add_argument(
        "--inject-anomalies",
        action="store_true",
        help="Plant data quality defects for the tests to catch.",
    )
    parser.add_argument(
        "--no-events",
        action="store_true",
        help="Skip the clickstream table, which dominates row counts.",
    )
    args = parser.parse_args(argv)

    preset = SCALE_PRESETS[args.scale]
    return Config(
        customers=args.customers or preset["customers"],
        days=args.days or preset["days"],
        seed=args.seed,
        end_date=args.end_date,
        out_dir=args.out,
        inject_anomalies=args.inject_anomalies,
        include_events=not args.no_events,
        scale_name=args.scale
        if not (args.customers or args.days)
        else f"custom({args.customers or preset['customers']}c/"
        f"{args.days or preset['days']}d)",
    )


def main(argv: list[str] | None = None) -> int:
    config = parse_args(argv)
    print(
        f"tradeflow generator | scale={config.scale_name} seed={config.seed} "
        f"| {config.start_date} -> {config.end_date} "
        f"| {config.customers:,} customers",
        flush=True,
    )
    if config.inject_anomalies:
        print("  anomaly injection ENABLED -- data quality tests should fail")

    stats = generate(config)

    width = max(len(name) for name in stats.rows)
    print(f"\nlanding zone written to {config.out_dir}/")
    for entity, count in sorted(stats.rows.items(), key=lambda kv: -kv[1]):
        print(f"  {entity:<{width}}  {count:>12,} rows")
    print(f"  {'TOTAL':<{width}}  {sum(stats.rows.values()):>12,} rows")
    if stats.anomalies:
        print("\n  anomalies injected:")
        for name, count in sorted(stats.anomalies.items()):
            print(f"    {name:<28} {count:>8,}")
    print(f"\ncompleted in {stats.elapsed_seconds}s")
    return 0


def _exit(code: int) -> None:
    """Terminate without running interpreter teardown.

    PyArrow's global thread pool intermittently deadlocks in its own destructor
    during ``exit()`` on macOS: ``arrow::internal::ThreadPool::Shutdown`` blocks
    on a condition variable that is never signalled, and the process sits at 0%
    CPU forever holding several GB. It reproduced reliably at ``--scale medium``
    and never at ``tiny``, so it scales with how hard the writer was worked.

    By the time we get here every Parquet file, the manifest and stdout have all
    been flushed, so there is nothing left for teardown to do. Skipping it turns
    an intermittent hang into a guaranteed clean exit.

    Confined to the CLI entrypoint on purpose: importing this module (from the
    Dagster asset, or from the tests) gets ordinary Python semantics.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    import os

    os._exit(code)


if __name__ == "__main__":
    _exit(main())
