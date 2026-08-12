/*
  One row per customer: lifetime trading behaviour and current portfolio state.

  Joins to the *current* version of dim_customer, which is the one case where
  filtering a Type 2 dimension on `is_current` is right rather than wrong. This
  model answers "who are our customers now and how are they doing" -- a
  present-tense question. The facts remain the place to ask what someone's risk
  rating was when they placed a particular trade.
*/

WITH customers AS (

  SELECT * FROM {{ ref('dim_customer') }}
  WHERE is_current

),

lifetime_trading AS (

  SELECT
    customer_id,
    COUNT(*) AS lifetime_fill_count,
    COUNT(DISTINCT date_day) AS trading_days,
    COUNT(DISTINCT instrument_id) AS distinct_instruments_traded,
    COUNT(DISTINCT sector) AS distinct_sectors_traded,
    SUM(gross_notional_reporting) AS lifetime_traded_notional_reporting,
    SUM(commission_reporting) AS lifetime_commission_reporting,
    MIN(date_day) AS first_trade_date,
    MAX(date_day) AS last_trade_date,
    AVG(gross_notional_reporting) AS mean_fill_notional_reporting,
    -- The instrument the customer has put the most money into.
    ARG_MAX(symbol, gross_notional_reporting) AS largest_trade_symbol,
    MODE(channel) AS primary_channel,
  FROM {{ ref('fct_executions') }}
  GROUP BY customer_id

),

lifetime_orders AS (

  SELECT
    account_id,
    customer_id,
    COUNT(*) AS lifetime_order_count,
    COUNT_IF(is_cancelled) AS lifetime_cancelled_count,
  FROM {{ ref('fct_orders') }}
  GROUP BY 1, 2

),

order_totals AS (

  SELECT
    customer_id,
    SUM(lifetime_order_count) AS lifetime_order_count,
    SUM(lifetime_cancelled_count) AS lifetime_cancelled_count,
  FROM lifetime_orders
  GROUP BY customer_id

),

-- Current portfolio state, from the most recent snapshot in the window. Taken
-- as an explicit join to the max date rather than a QUALIFY, because a window
-- function is evaluated after GROUP BY and cannot filter the rows going into it.
-- Accounts closed before that date correctly drop out: a closed account holds
-- no equity.
latest_snapshot_date AS (

  SELECT MAX(snapshot_date) AS snapshot_date
  FROM {{ ref('fct_account_daily') }}

),

latest_positions AS (

  SELECT
    accounts.customer_id,
    SUM(snapshot.account_equity_reporting) AS account_equity_reporting,
    SUM(snapshot.cash_balance_reporting) AS cash_balance_reporting,
    SUM(snapshot.holdings_value_reporting) AS holdings_value_reporting,
    SUM(snapshot.net_funded_reporting) AS net_funded_reporting,
    SUM(snapshot.unrealised_gain_reporting) AS unrealised_gain_reporting,
    SUM(snapshot.realised_gain_reporting) AS realised_gain_reporting,
    SUM(snapshot.open_position_count) AS open_position_count,
    COUNT(*) AS account_count,
  FROM {{ ref('fct_account_daily') }} AS snapshot
  INNER JOIN {{ ref('dim_account') }} AS accounts
    ON snapshot.account_id = accounts.account_id
  INNER JOIN latest_snapshot_date
    ON snapshot.snapshot_date = latest_snapshot_date.snapshot_date
  GROUP BY accounts.customer_id

),

engagement AS (

  SELECT
    customer_id,
    COUNT(*) AS lifetime_event_count,
    COUNT(DISTINCT session_id) AS lifetime_session_count,
    COUNT(DISTINCT event_date) AS active_days,
    MAX(occurred_at) AS last_seen_at,
    MODE(device_family) AS primary_device_family,
  FROM {{ ref('stg_app_events') }}
  GROUP BY customer_id

)

SELECT
  customers.customer_key,
  customers.customer_id,
  customers.full_name,
  customers.email,
  customers.country_code,
  customers.customer_tier,
  customers.risk_rating,
  customers.kyc_status,
  customers.age_band,
  customers.marketing_opt_in,
  customers.signup_date,
  customers.signup_month,
  DATEDIFF('day', customers.signup_date, CURRENT_DATE) AS tenure_days,

  COALESCE(latest_positions.account_count, 0) AS account_count,
  COALESCE(latest_positions.account_equity_reporting, 0)
    AS account_equity_reporting,
  COALESCE(latest_positions.cash_balance_reporting, 0) AS cash_balance_reporting,
  COALESCE(latest_positions.holdings_value_reporting, 0)
    AS holdings_value_reporting,
  COALESCE(latest_positions.net_funded_reporting, 0) AS net_funded_reporting,
  COALESCE(latest_positions.unrealised_gain_reporting, 0)
    AS unrealised_gain_reporting,
  COALESCE(latest_positions.realised_gain_reporting, 0)
    AS realised_gain_reporting,
  COALESCE(latest_positions.unrealised_gain_reporting, 0)
    + COALESCE(latest_positions.realised_gain_reporting, 0)
    AS total_gain_reporting,
  COALESCE(latest_positions.open_position_count, 0) AS open_position_count,

  COALESCE(lifetime_trading.lifetime_fill_count, 0) AS lifetime_fill_count,
  COALESCE(order_totals.lifetime_order_count, 0) AS lifetime_order_count,
  COALESCE(order_totals.lifetime_cancelled_count, 0) AS lifetime_cancelled_count,
  COALESCE(lifetime_trading.lifetime_traded_notional_reporting, 0)
    AS lifetime_traded_notional_reporting,
  COALESCE(lifetime_trading.lifetime_commission_reporting, 0)
    AS lifetime_commission_reporting,
  lifetime_trading.mean_fill_notional_reporting,
  lifetime_trading.trading_days,
  lifetime_trading.distinct_instruments_traded,
  lifetime_trading.distinct_sectors_traded,
  lifetime_trading.first_trade_date,
  lifetime_trading.last_trade_date,
  lifetime_trading.largest_trade_symbol,
  lifetime_trading.primary_channel,

  COALESCE(engagement.lifetime_event_count, 0) AS lifetime_event_count,
  COALESCE(engagement.lifetime_session_count, 0) AS lifetime_session_count,
  COALESCE(engagement.active_days, 0) AS app_active_days,
  engagement.last_seen_at,
  engagement.primary_device_family,

  -- Return on capital actually put in. NULLIF rather than a CASE: a customer who
  -- has funded nothing has an undefined return, not a zero one, and a zero would
  -- quietly drag every cohort average towards the middle.
  CAST(
    (
      COALESCE(latest_positions.unrealised_gain_reporting, 0)
      + COALESCE(latest_positions.realised_gain_reporting, 0)
    ) / NULLIF(latest_positions.net_funded_reporting, 0) AS DECIMAL(12, 6)
  ) AS return_on_funded,
  CAST(
    COALESCE(order_totals.lifetime_cancelled_count, 0)
    / NULLIF(order_totals.lifetime_order_count, 0) AS DECIMAL(9, 6)
  ) AS cancellation_rate,
  COALESCE(lifetime_trading.lifetime_fill_count, 0) > 0 AS has_ever_traded,
FROM customers
LEFT JOIN lifetime_trading
  ON customers.customer_id = lifetime_trading.customer_id
LEFT JOIN order_totals ON customers.customer_id = order_totals.customer_id
LEFT JOIN latest_positions
  ON customers.customer_id = latest_positions.customer_id
LEFT JOIN engagement ON customers.customer_id = engagement.customer_id
