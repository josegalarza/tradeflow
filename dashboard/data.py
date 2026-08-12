"""Warehouse access for the dashboard.

Every query the dashboard runs lives here, and every one of them reads a mart --
never staging, never intermediate. That is the layered architecture being taken
seriously rather than described: if a chart needs a number the marts do not have,
the fix is a model, not a join in the presentation layer.

The connection is read-only. A dashboard has no business writing to the
warehouse, and read_only=True means a stray statement fails loudly instead of
mutating something at 2am.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import duckdb
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE = REPO_ROOT / "data" / "tradeflow.duckdb"

REPORTING_CURRENCY = "USD"


class WarehouseUnavailable(RuntimeError):
    """The warehouse file is missing or unbuilt."""


def database_path() -> Path:
    return Path(os.environ.get("TRADEFLOW_DUCKDB", str(DEFAULT_DATABASE)))


def connect() -> duckdb.DuckDBPyConnection:
    path = database_path()
    if not path.exists():
        raise WarehouseUnavailable(
            f"no warehouse at {path}. Run `make demo` first -- the dashboard reads "
            "the marts, it does not build them."
        )
    return duckdb.connect(str(path), read_only=True)


def query(sql: str, params: list | None = None) -> pd.DataFrame:
    with connect() as connection:
        return connection.execute(sql, params or []).df()


# ---------------------------------------------------------------------------- #
# Headline figures
# ---------------------------------------------------------------------------- #


@lru_cache(maxsize=1)
def kpis() -> dict[str, float]:
    """Top-line numbers for the overview page.

    One query rather than eight. Each of these is a scan of an aggregate mart,
    and eight round trips to render four tiles is the kind of thing that makes a
    dashboard feel slow for no reason.
    """
    frame = query(
        """
        WITH latest AS (
            SELECT MAX(snapshot_date) AS snapshot_date FROM marts.fct_account_daily
        ),
        equity AS (
            SELECT
                SUM(account_equity_reporting) AS total_equity,
                SUM(cash_balance_reporting)   AS total_cash,
                SUM(holdings_value_reporting) AS total_holdings,
                SUM(net_funded_reporting)     AS total_funded,
                SUM(unrealised_gain_reporting) AS unrealised,
                SUM(realised_gain_reporting)   AS realised,
                COUNT(DISTINCT account_id)     AS open_accounts
            FROM marts.fct_account_daily
            WHERE snapshot_date = (SELECT snapshot_date FROM latest)
        ),
        activity AS (
            SELECT
                SUM(order_count)               AS lifetime_orders,
                SUM(fill_count)                AS lifetime_fills,
                SUM(traded_notional_reporting) AS lifetime_notional,
                SUM(commission_reporting)      AS lifetime_commission
            FROM marts.agg_daily_trading_activity
        ),
        customers AS (
            SELECT
                COUNT(*)                       AS customers,
                COUNT_IF(has_ever_traded)      AS trading_customers
            FROM marts.agg_customer_performance
        ),
        quality AS (
            SELECT
                SUM(total_rejected_rows) AS rejected_rows,
                SUM(total_rows)          AS screened_rows
            FROM marts.agg_data_quality
        )
        SELECT * FROM equity, activity, customers, quality, latest
        """
    )
    record = frame.iloc[0].to_dict()
    record["reject_rate"] = (
        record["rejected_rows"] / record["screened_rows"]
        if record.get("screened_rows")
        else 0.0
    )
    return record


def daily_activity(channels: list[str] | None = None) -> pd.DataFrame:
    sql = """
        SELECT
            date_day,
            SUM(order_count)               AS orders,
            SUM(fill_count)                AS fills,
            SUM(traded_notional_reporting) AS notional,
            SUM(commission_reporting)      AS commission,
            SUM(cancelled_order_count)     AS cancelled,
            SUM(trading_accounts)          AS trading_accounts
        FROM marts.agg_daily_trading_activity
        {where}
        GROUP BY date_day
        ORDER BY date_day
    """
    if channels:
        placeholders = ", ".join("?" for _ in channels)
        return query(sql.format(where=f"WHERE channel IN ({placeholders})"), channels)
    return query(sql.format(where=""))


def equity_curve() -> pd.DataFrame:
    return query(
        """
        SELECT
            snapshot_date,
            SUM(cash_balance_reporting)    AS cash,
            SUM(holdings_value_reporting)  AS holdings,
            SUM(account_equity_reporting)  AS equity,
            SUM(net_funded_reporting)      AS net_funded
        FROM marts.fct_account_daily
        GROUP BY snapshot_date
        ORDER BY snapshot_date
        """
    )


def notional_by_channel() -> pd.DataFrame:
    return query(
        """
        SELECT channel, asset_class, SUM(traded_notional_reporting) AS notional
        FROM marts.agg_daily_trading_activity
        GROUP BY channel, asset_class
        ORDER BY notional DESC
        """
    )


def orders_by_hour() -> pd.DataFrame:
    return query(
        """
        SELECT placed_hour, order_status, COUNT(*) AS orders
        FROM marts.fct_orders
        GROUP BY placed_hour, order_status
        ORDER BY placed_hour
        """
    )


def top_instruments(limit: int = 15) -> pd.DataFrame:
    return query(
        """
        SELECT
            executions.symbol,
            instruments.sector,
            instruments.asset_class,
            SUM(executions.gross_notional_reporting) AS notional,
            COUNT(*)                                 AS fills,
            COUNT(DISTINCT executions.account_id)     AS accounts
        FROM marts.fct_executions AS executions
        INNER JOIN marts.dim_instrument AS instruments
            ON executions.instrument_key = instruments.instrument_key
        GROUP BY 1, 2, 3
        ORDER BY notional DESC
        LIMIT ?
        """,
        [limit],
    )


def sector_exposure() -> pd.DataFrame:
    return query(
        """
        SELECT
            sector,
            SUM(market_value_reporting)   AS market_value,
            SUM(unrealised_gain_reporting) AS unrealised_gain,
            COUNT(DISTINCT account_id)     AS holders
        FROM marts.fct_positions_daily
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM marts.fct_positions_daily)
        GROUP BY sector
        ORDER BY market_value DESC
        """
    )


def customer_cohorts() -> pd.DataFrame:
    return query(
        """
        SELECT
            signup_month,
            customer_tier,
            COUNT(*)                                     AS customers,
            SUM(account_equity_reporting)                AS equity,
            SUM(lifetime_traded_notional_reporting)      AS notional,
            AVG(lifetime_fill_count)                     AS mean_fills
        FROM marts.agg_customer_performance
        GROUP BY signup_month, customer_tier
        ORDER BY signup_month, customer_tier
        """
    )


def customer_value_distribution() -> pd.DataFrame:
    """Equity vs commission per customer, for the value scatter.

    Reads the aggregate, not dim_customer -- so nothing identifying reaches the
    presentation layer even before the secure views are considered.
    """
    return query(
        """
        SELECT
            customer_tier,
            risk_rating,
            age_band,
            account_equity_reporting     AS equity,
            lifetime_commission_reporting AS commission,
            lifetime_fill_count           AS fills,
            return_on_funded
        FROM marts.agg_customer_performance
        WHERE has_ever_traded
        """
    )


# ---------------------------------------------------------------------------- #
# Data quality and governance
# ---------------------------------------------------------------------------- #


def quality_by_reason() -> pd.DataFrame:
    return query(
        """
        SELECT model_name, reject_reason, SUM(rejected_rows) AS rows
        FROM marts.agg_data_quality
        WHERE reject_reason <> 'none'
        GROUP BY 1, 2
        ORDER BY rows DESC
        """
    )


def quality_over_time() -> pd.DataFrame:
    return query(
        """
        SELECT
            activity_date,
            model_name,
            ANY_VALUE(total_rows)           AS total_rows,
            ANY_VALUE(total_rejected_rows)  AS rejected_rows,
            ANY_VALUE(overall_reject_rate)  AS reject_rate
        FROM marts.agg_data_quality
        GROUP BY activity_date, model_name
        ORDER BY activity_date
        """
    )


def stale_price_share() -> pd.DataFrame:
    """How much of the position snapshot is priced from an earlier session.

    Around a quarter, by design -- positions exist every day and equities are only
    priced on trading days. Charted because a number that is *supposed* to be 28%
    is only reassuring if you can see it is still 28%.
    """
    return query(
        """
        SELECT
            snapshot_date,
            COUNT(*)                                        AS positions,
            COUNT_IF(is_stale_price)                        AS stale,
            COUNT_IF(is_stale_price) * 1.0 / COUNT(*)       AS stale_share
        FROM marts.fct_positions_daily
        GROUP BY snapshot_date
        ORDER BY snapshot_date
        """
    )


def classification_summary() -> pd.DataFrame:
    """Column counts by classification, straight from the governance tooling."""
    from governance.policy import Policy, load_models

    policy = Policy.load()
    models = load_models(policy=policy, include_generated=False)
    counts: dict[str, int] = dict.fromkeys(policy.classifications, 0)
    for model in models:
        for column in model.columns:
            if column.in_database:
                counts[column.classification] = counts.get(column.classification, 0) + 1
    return pd.DataFrame(
        [
            {
                "classification": name,
                "columns": counts.get(name, 0),
                "rank": policy.rank(name),
            }
            for name in policy.classifications
        ]
    ).sort_values("rank")


def pii_register() -> pd.DataFrame:
    """Every PII column and how each role sees it."""
    from governance.policy import Policy, load_models

    policy = Policy.load()
    models = load_models(policy=policy, include_generated=False)
    rows = []
    for model in models:
        for column in model.columns:
            if not (column.is_pii and column.in_database):
                continue
            row = {
                "model": model.name,
                "column": column.name,
                "category": column.pii_type or "-",
                "classification": column.classification,
            }
            if policy.in_secure_scope(model):
                for role in sorted(policy.roles):
                    if policy.is_dropped_for_role(column, role):
                        row[role] = "withheld"
                    else:
                        strategy = policy.resolve_masking(column, role)
                        row[role] = "clear" if strategy == "none" else strategy
            else:
                for role in sorted(policy.roles):
                    row[role] = "n/a"
            rows.append(row)
    return pd.DataFrame(rows)


def warehouse_inventory() -> pd.DataFrame:
    return query(
        """
        SELECT schema_name AS layer, table_name, estimated_size AS rows
        FROM duckdb_tables()
        WHERE schema_name NOT IN ('dq_failures', 'information_schema')
        ORDER BY schema_name, table_name
        """
    )


def generator_manifest() -> dict:
    """Provenance: what generated the data currently in the warehouse."""
    import json

    path = (
        Path(
            os.environ.get("TRADEFLOW_LANDING_PATH", str(REPO_ROOT / "data" / "landing"))
        )
        / "_manifest.json"
    )
    if not path.exists():
        return {}
    return json.loads(path.read_text())
