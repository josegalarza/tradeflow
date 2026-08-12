"""Tests for the synthetic data generator.

These assert the *invariants the warehouse depends on*, not the generator's
internals. Every one of them corresponds to a promise the dbt tests would
otherwise discover only after a full build: quantities are positive, fills sum to
their order, nothing precedes the account it belongs to.

Two of these were written after the bug they describe. That is noted where it
applies, because a regression test with a story is easier to respect than one
without.
"""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from ingestion.generate import (
    BUY_PROBABILITY,
    Config,
    build_calendar,
    dictionary_encode,
    generate,
    parse_args,
    split_quantity,
)

END_DATE = date(2026, 8, 1)


@pytest.fixture(scope="module")
def landing(tmp_path_factory) -> dict:
    """Generate a small deterministic dataset once, read it with DuckDB."""
    import duckdb

    out = tmp_path_factory.mktemp("landing")
    config = Config(
        customers=120,
        days=90,
        seed=7,
        end_date=END_DATE,
        out_dir=out,
        scale_name="test",
    )
    stats = generate(config)

    connection = duckdb.connect()
    for entity in stats.rows:
        if stats.rows[entity] == 0:
            continue
        connection.execute(
            f"""
            CREATE VIEW {entity} AS
            SELECT * FROM read_parquet('{out}/{entity}/**/*.parquet',
                                       hive_partitioning = true)
            """
        )
    return {"connection": connection, "stats": stats, "path": out}


# ---------------------------------------------------------------------------- #
# Determinism and configuration
# ---------------------------------------------------------------------------- #


def test_same_seed_produces_identical_row_counts(tmp_path):
    """Determinism is what lets CI assert anything at all about the data."""
    counts = []
    for run in range(2):
        config = Config(
            customers=60,
            days=60,
            seed=99,
            end_date=END_DATE,
            out_dir=tmp_path / f"run{run}",
            scale_name="test",
        )
        counts.append(generate(config).rows)
    assert counts[0] == counts[1]


def test_different_seed_produces_different_data(tmp_path):
    """A seed that does not change the output is not a seed."""
    rows = []
    for seed in (1, 2):
        config = Config(
            customers=60,
            days=60,
            seed=seed,
            end_date=END_DATE,
            out_dir=tmp_path / f"seed{seed}",
            scale_name="test",
        )
        rows.append(generate(config).rows)
    assert rows[0] != rows[1]


def test_scale_presets_are_ordered():
    """A larger preset must actually be larger, or --scale means nothing."""
    sizes = [
        parse_args(["--scale", name]).customers for name in ("tiny", "small", "medium")
    ]
    assert sizes == sorted(sizes)
    assert len(set(sizes)) == len(sizes)


def test_custom_overrides_beat_the_preset():
    config = parse_args(["--scale", "large", "--customers", "42", "--days", "7"])
    assert (config.customers, config.days) == (42, 7)
    assert "custom" in config.scale_name


def test_manifest_records_provenance(landing):
    manifest = json.loads((landing["path"] / "_manifest.json").read_text())
    assert manifest["seed"] == 7
    assert manifest["customers"] == 120
    assert manifest["total_rows"] == sum(manifest["row_counts"].values())
    assert manifest["anomalies_injected"] is False


# ---------------------------------------------------------------------------- #
# Referential integrity
# ---------------------------------------------------------------------------- #


def test_no_orphan_foreign_keys(landing):
    connection = landing["connection"]
    orphan_orders = connection.execute(
        """
        SELECT COUNT(*) FROM orders
        LEFT JOIN accounts USING (account_id)
        WHERE accounts.account_id IS NULL
        """
    ).fetchone()[0]
    orphan_fills = connection.execute(
        """
        SELECT COUNT(*) FROM executions
        LEFT JOIN orders USING (order_id)
        WHERE orders.order_id IS NULL
        """
    ).fetchone()[0]
    assert (orphan_orders, orphan_fills) == (0, 0)


def test_primary_keys_are_unique(landing):
    connection = landing["connection"]
    for entity, key in [
        ("orders", "order_id"),
        ("executions", "execution_id"),
        ("accounts", "account_id"),
        ("cash_movements", "movement_id"),
        ("app_events", "event_id"),
    ]:
        duplicates = connection.execute(
            f"SELECT COUNT(*) FROM (SELECT {key} FROM {entity} "
            f"GROUP BY 1 HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        assert duplicates == 0, f"{entity}.{key} has {duplicates} duplicated values"


def test_customer_extracts_are_one_row_per_customer_per_date(landing):
    duplicates = (
        landing["connection"]
        .execute(
            """
        SELECT COUNT(*) FROM (
            SELECT customer_id, extract_date FROM customer_extracts
            GROUP BY 1, 2 HAVING COUNT(*) > 1
        )
        """
        )
        .fetchone()[0]
    )
    assert duplicates == 0


# ---------------------------------------------------------------------------- #
# Domain invariants
# ---------------------------------------------------------------------------- #


def test_quantities_are_positive(landing):
    """Regression test.

    Small orders that partially filled used to floor to a zero-quantity fill --
    which is not a partial fill, it is a fill that did not happen. Caught by the
    dbt test `execution_quantity > 0` on the first real build.
    """
    connection = landing["connection"]
    assert (
        connection.execute("SELECT COUNT(*) FROM orders WHERE quantity <= 0").fetchone()[
            0
        ]
        == 0
    )
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM executions WHERE quantity <= 0"
        ).fetchone()[0]
        == 0
    )


def test_filled_orders_are_filled_exactly(landing):
    """A `filled` order's fills must sum to its quantity -- not approximately."""
    mismatched = (
        landing["connection"]
        .execute(
            """
        SELECT COUNT(*) FROM (
            SELECT
                executions.order_id,
                SUM(executions.quantity)     AS filled,
                ANY_VALUE(orders.quantity)   AS ordered
            FROM executions
            INNER JOIN orders USING (order_id)
            WHERE orders.order_status = 'filled'
            GROUP BY executions.order_id
            HAVING ABS(filled - ordered) > 0.00000001
        )
        """
        )
        .fetchone()[0]
    )
    assert mismatched == 0


def test_no_order_is_over_filled(landing):
    over_filled = (
        landing["connection"]
        .execute(
            """
        SELECT COUNT(*) FROM (
            SELECT executions.order_id
            FROM executions
            INNER JOIN orders USING (order_id)
            GROUP BY executions.order_id
            HAVING SUM(executions.quantity)
                 > ANY_VALUE(orders.quantity) + 0.00000001
        )
        """
        )
        .fetchone()[0]
    )
    assert over_filled == 0


def test_cancelled_orders_have_no_fills(landing):
    fills = (
        landing["connection"]
        .execute(
            """
        SELECT COUNT(*) FROM executions
        INNER JOIN orders USING (order_id)
        WHERE orders.order_status IN ('cancelled', 'rejected')
        """
        )
        .fetchone()[0]
    )
    assert fills == 0


def test_fills_never_precede_their_order(landing):
    early = (
        landing["connection"]
        .execute(
            """
        SELECT COUNT(*) FROM executions
        INNER JOIN orders USING (order_id)
        WHERE executions.executed_at < orders.placed_at
        """
        )
        .fetchone()[0]
    )
    assert early == 0


def test_nothing_happens_before_its_account_opens(landing):
    """Regression test.

    An order placed on the final Saturday of the window had no next trading
    session to roll into, so it rolled *backwards* -- landing before the account
    that placed it existed. Surfaced as twelve unexplained rows in the warehouse's
    cash reconciliation test.
    """
    connection = landing["connection"]
    for entity, column in [
        ("orders", "placed_date"),
        ("executions", "executed_date"),
        ("cash_movements", "occurred_date"),
    ]:
        join = (
            "INNER JOIN orders USING (order_id) "
            "INNER JOIN accounts ON orders.account_id = accounts.account_id"
            if entity == "executions"
            else f"INNER JOIN accounts ON {entity}.account_id = accounts.account_id"
        )
        early = connection.execute(
            f"""
            SELECT COUNT(*) FROM {entity} {join}
            WHERE CAST({entity}.{column} AS DATE) < CAST(accounts.opened_at AS DATE)
            """
        ).fetchone()[0]
        assert early == 0, f"{entity} has {early} rows before its account opened"


def test_equities_only_trade_on_trading_days(landing):
    """Weekend equity orders roll into Monday; crypto is exempt."""
    weekend = (
        landing["connection"]
        .execute(
            """
        SELECT COUNT(*) FROM orders
        INNER JOIN instruments USING (instrument_id)
        WHERE instruments.asset_class <> 'crypto'
          AND DAYOFWEEK(CAST(orders.placed_date AS DATE)) IN (0, 6)
        """
        )
        .fetchone()[0]
    )
    assert weekend == 0


def test_execution_prices_sit_inside_the_daily_range(landing):
    outside = (
        landing["connection"]
        .execute(
            """
        SELECT COUNT(*)
        FROM executions
        INNER JOIN orders USING (order_id)
        INNER JOIN market_prices AS prices
            ON prices.instrument_id = orders.instrument_id
            AND prices.price_date = CAST(executions.executed_date AS DATE)
        WHERE executions.execution_price < prices.low_price - 0.000001
           OR executions.execution_price > prices.high_price + 0.000001
        """
        )
        .fetchone()[0]
    )
    assert outside == 0


def test_ohlc_bands_are_coherent(landing):
    broken = (
        landing["connection"]
        .execute(
            """
        SELECT COUNT(*) FROM market_prices
        WHERE close_price NOT BETWEEN low_price AND high_price
           OR open_price NOT BETWEEN low_price AND high_price
           OR low_price <= 0
        """
        )
        .fetchone()[0]
    )
    assert broken == 0


def test_fx_covers_every_day_and_currency(landing):
    """The warehouse INNER JOINs to FX, so a gap silently drops fills."""
    gaps = (
        landing["connection"]
        .execute(
            """
        WITH needed AS (
            SELECT DISTINCT currency, CAST(executed_date AS DATE) AS rate_date
            FROM executions
        )
        SELECT COUNT(*) FROM needed
        LEFT JOIN fx_rates
            ON fx_rates.base_currency = needed.currency
            AND fx_rates.rate_date = needed.rate_date
            AND fx_rates.quote_currency = 'USD'
        WHERE fx_rates.rate IS NULL
        """
        )
        .fetchone()[0]
    )
    assert gaps == 0


def test_buy_share_is_close_to_the_configured_probability(landing):
    """The funding model is derived from BUY_PROBABILITY, so it has to hold.

    The tolerance is four standard errors of a binomial proportion, not a fixed
    margin. A fixed margin is wrong in both directions: too tight at small n, so
    the test flakes on ordinary sampling noise, and far too loose at large n,
    where it would wave through a genuine bias. This version tightens
    automatically as the dataset grows.
    """
    share, orders = (
        landing["connection"]
        .execute(
            "SELECT AVG(CASE WHEN side = 'buy' THEN 1.0 ELSE 0.0 END), COUNT(*) FROM orders"
        )
        .fetchone()
    )
    standard_error = (BUY_PROBABILITY * (1 - BUY_PROBABILITY) / orders) ** 0.5
    tolerance = 4 * standard_error
    assert abs(share - BUY_PROBABILITY) < tolerance, (
        f"buy share {share:.4f} deviates from {BUY_PROBABILITY} by more than "
        f"4 standard errors ({tolerance:.4f}) over {orders:,} orders"
    )


def test_pii_columns_are_populated(landing):
    """The classification framework needs real values to be worth demonstrating."""
    row = (
        landing["connection"]
        .execute(
            """
        SELECT
            COUNT(*) FILTER (WHERE email IS NULL)       AS null_emails,
            COUNT(*) FILTER (WHERE national_id IS NULL) AS null_ids,
            COUNT(DISTINCT email)                       AS distinct_emails,
            COUNT(DISTINCT customer_id)                 AS customers
        FROM customer_extracts
        """
        )
        .fetchone()
    )
    null_emails, null_ids, distinct_emails, customers = row
    assert null_emails == 0
    assert null_ids == 0
    # Emails carry the customer number, so they are unique by construction even
    # though the identity pool is reused.
    assert distinct_emails >= customers


def test_scd2_has_something_to_track(landing):
    """Without attribute drift the Type 2 dimension is a Type 1 with extra columns."""
    changed = (
        landing["connection"]
        .execute(
            """
        SELECT COUNT(*) FROM (
            SELECT customer_id
            FROM customer_extracts
            GROUP BY customer_id
            HAVING COUNT(DISTINCT
                kyc_status || risk_rating || customer_tier || email
                || street_address || CAST(marketing_opt_in AS VARCHAR)
            ) > 1
        )
        """
        )
        .fetchone()[0]
    )
    assert changed > 0


# ---------------------------------------------------------------------------- #
# Anomaly injection
# ---------------------------------------------------------------------------- #


def test_anomaly_injection_actually_breaks_things(tmp_path):
    """A quality suite that has never caught anything proves nothing.

    So the defects must be real: this asserts that injection produces the
    violations the dbt tests are written to detect.
    """
    import duckdb

    out = tmp_path / "anomalies"
    config = Config(
        customers=120,
        days=90,
        seed=7,
        end_date=END_DATE,
        out_dir=out,
        inject_anomalies=True,
        scale_name="test",
    )
    stats = generate(config)

    assert stats.anomalies, "no anomalies were recorded"
    expected = {
        "duplicate_executions",
        "over_filled_orders",
        "executions_before_order",
        "orphan_orders",
        "negative_quantities",
        "null_emails",
    }
    assert expected <= set(stats.anomalies)

    connection = duckdb.connect()
    for entity in ("orders", "executions", "customer_extracts", "accounts"):
        connection.execute(
            f"CREATE VIEW {entity} AS SELECT * FROM "
            f"read_parquet('{out}/{entity}/**/*.parquet', hive_partitioning = true)"
        )

    assert (
        connection.execute("SELECT COUNT(*) FROM orders WHERE quantity <= 0").fetchone()[
            0
        ]
        > 0
    )
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM (SELECT execution_id FROM executions "
            "GROUP BY 1 HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        > 0
    )
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM customer_extracts WHERE email IS NULL"
        ).fetchone()[0]
        > 0
    )
    assert (
        connection.execute(
            "SELECT COUNT(*) FROM orders LEFT JOIN accounts USING (account_id) "
            "WHERE accounts.account_id IS NULL"
        ).fetchone()[0]
        > 0
    )


# ---------------------------------------------------------------------------- #
# Unit-level helpers
# ---------------------------------------------------------------------------- #


def test_split_quantity_is_exact():
    """Fills must sum to their order exactly -- a dbt invariant depends on it."""
    rng = np.random.default_rng(0)
    totals = np.array([1.0, 2.0, 7.0, 100.0, 3.0])
    parts = np.array([1, 2, 3, 3, 3])
    groups, pieces = split_quantity(rng, totals, parts)
    sums = np.bincount(groups, weights=pieces, minlength=len(totals))
    assert np.allclose(sums, totals)
    assert (pieces >= 1).all(), "every fill must carry at least one unit"


def test_split_quantity_handles_single_part():
    rng = np.random.default_rng(0)
    _, pieces = split_quantity(rng, np.array([5.0]), np.array([1]))
    assert pieces.tolist() == [5.0]


def test_calendar_rolls_closed_days_forward():
    config = Config(
        customers=1,
        days=30,
        seed=1,
        end_date=date(2026, 6, 30),
        out_dir=None,  # not written
        scale_name="test",
    )
    calendar = build_calendar(config)
    # Every resolved session index must land on an actual trading day.
    sessions = calendar.loc[calendar["next_session_index"], "is_trading_day"]
    assert sessions.all()


def test_dictionary_encode_skips_the_partition_column():
    """Arrow cannot sort a dictionary column, and the partition key gets sorted."""
    frame = pd.DataFrame(
        {
            "event_date": ["2026-01-01"] * 50,
            "venue": ["A", "B"] * 25,
            "value": range(50),
        }
    )
    encoded = dictionary_encode(frame, skip={"event_date"})
    assert encoded["event_date"].dtype == object
    assert str(encoded["venue"].dtype) == "category"
    assert encoded["value"].dtype == frame["value"].dtype
