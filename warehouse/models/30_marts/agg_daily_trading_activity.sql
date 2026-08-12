/*
  Daily trading activity by channel and asset class.

  Exists for speed, not capability: every number here is derivable from
  fct_executions and fct_orders, but the dashboard's landing page would
  otherwise scan the atomic facts on every filter change. Aggregates are a
  performance decision, and the moment one of them can answer a question the
  facts cannot, the warehouse has two versions of the truth.

  Grain is deliberately coarse enough to stay small (days x channels x asset
  classes) and fine enough that the dashboard's filters never need the atomic
  tables.
*/

WITH orders AS (

  SELECT
    date_day,
    channel,
    asset_class,
    COUNT(*) AS order_count,
    COUNT(DISTINCT account_id) AS trading_accounts,
    COUNT(DISTINCT customer_key) AS trading_customers,
    SUM(order_quantity) AS ordered_quantity,
    COUNT_IF(is_fully_filled) AS filled_order_count,
    COUNT_IF(is_cancelled) AS cancelled_order_count,
    COUNT_IF(is_rejected) AS rejected_order_count,
    AVG(seconds_to_first_fill) AS mean_seconds_to_first_fill,
    MEDIAN(seconds_to_first_fill) AS median_seconds_to_first_fill,
  FROM {{ ref('fct_orders') }}
  GROUP BY 1, 2, 3

),

executions AS (

  SELECT
    date_day,
    channel,
    asset_class,
    COUNT(*) AS fill_count,
    SUM(gross_notional_reporting) AS traded_notional_reporting,
    SUM(commission_reporting) AS commission_reporting,
    SUM(CASE WHEN side = 'buy' THEN gross_notional_reporting ELSE 0 END)
      AS buy_notional_reporting,
    SUM(CASE WHEN side = 'sell' THEN gross_notional_reporting ELSE 0 END)
      AS sell_notional_reporting,
    AVG(slippage_vs_close) AS mean_slippage_vs_close,
    COUNT(DISTINCT venue) AS venues_used,
    COUNT(DISTINCT instrument_id) AS instruments_traded,
  FROM {{ ref('fct_executions') }}
  GROUP BY 1, 2, 3

)

SELECT
  COALESCE(orders.date_day, executions.date_day) AS date_day,
  COALESCE(orders.channel, executions.channel) AS channel,
  COALESCE(orders.asset_class, executions.asset_class) AS asset_class,

  COALESCE(orders.order_count, 0) AS order_count,
  COALESCE(orders.filled_order_count, 0) AS filled_order_count,
  COALESCE(orders.cancelled_order_count, 0) AS cancelled_order_count,
  COALESCE(orders.rejected_order_count, 0) AS rejected_order_count,
  COALESCE(orders.trading_accounts, 0) AS trading_accounts,
  COALESCE(orders.trading_customers, 0) AS trading_customers,
  orders.ordered_quantity,
  orders.mean_seconds_to_first_fill,
  orders.median_seconds_to_first_fill,

  COALESCE(executions.fill_count, 0) AS fill_count,
  COALESCE(executions.traded_notional_reporting, 0) AS traded_notional_reporting,
  COALESCE(executions.buy_notional_reporting, 0) AS buy_notional_reporting,
  COALESCE(executions.sell_notional_reporting, 0) AS sell_notional_reporting,
  COALESCE(executions.buy_notional_reporting, 0)
    - COALESCE(executions.sell_notional_reporting, 0) AS net_flow_reporting,
  COALESCE(executions.commission_reporting, 0) AS commission_reporting,
  executions.mean_slippage_vs_close,
  COALESCE(executions.venues_used, 0) AS venues_used,
  COALESCE(executions.instruments_traded, 0) AS instruments_traded,

  -- Rates, computed once here rather than in every chart. NULLIF guards the
  -- day-with-no-orders case, where a naive ratio would divide by zero.
  CAST(
    COALESCE(orders.cancelled_order_count, 0)
    / NULLIF(orders.order_count, 0) AS DECIMAL(9, 6)
  ) AS cancellation_rate,
  CAST(
    COALESCE(orders.filled_order_count, 0)
    / NULLIF(orders.order_count, 0) AS DECIMAL(9, 6)
  ) AS fill_rate,
  CAST(
    COALESCE(executions.fill_count, 0)
    / NULLIF(orders.filled_order_count, 0) AS DECIMAL(9, 4)
  ) AS fills_per_filled_order,
FROM orders
FULL OUTER JOIN executions
  ON orders.date_day = executions.date_day
  AND orders.channel = executions.channel
  AND orders.asset_class = executions.asset_class
