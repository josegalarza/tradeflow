/*
  Transaction fact. One row per fill -- the atomic grain of this warehouse.

  Every measure here is fully additive across every dimension: quantity,
  notional, commission. That is what makes it a transaction fact, and it is why
  this table can answer questions nobody has asked yet. The aggregates exist for
  speed, not for capability.

  The customer key is resolved as-of the execution date, which is the join most
  often got wrong in the presence of a Type 2 dimension. Two mistakes are
  common: joining on `is_current` (which attributes every historical trade to
  the customer's attributes today) and joining on customer_id alone (which
  multiplies every fill by the customer's version count). The ASOF JOIN below
  picks the one version whose window contains the execution date.

  DuckDB's ASOF JOIN does the "greatest key less than or equal to" match
  directly. The equivalent portable form is a BETWEEN range join, which is
  correct but materially slower -- and this is the join that runs against the
  largest table in the warehouse.
*/

WITH executions AS (

  SELECT * FROM {{ ref('int_executions_priced') }}

),

customer_versions AS (

  SELECT
    customer_key,
    customer_id,
    valid_from,
    valid_to,
  FROM {{ ref('dim_customer') }}

),

instruments AS (

  SELECT
    instrument_key,
    instrument_id,
    asset_class,
    sector,
    symbol,
  FROM {{ ref('dim_instrument') }}

),

accounts AS (

  SELECT
    account_key,
    account_id,
  FROM {{ ref('dim_account') }}

),

daily_prices AS (

  SELECT
    instrument_id,
    price_date,
    close_price,
    open_price,
  FROM {{ ref('stg_market_prices') }}

)

SELECT
  -- Degenerate dimension: the fill's own identifier, carried for traceability
  -- back to the source system rather than for joining.
  executions.execution_id,
  executions.order_id,

  -- Foreign keys
  accounts.account_key,
  customer_versions.customer_key,
  instruments.instrument_key,
  executions.executed_date AS date_day,

  -- Natural keys, kept alongside the surrogates. Every real warehouse gets
  -- asked "which account is that?" and nobody wants to join to find out.
  executions.account_id,
  executions.customer_id,
  executions.instrument_id,
  instruments.symbol,

  -- Dimensional attributes at transaction time
  executions.side,
  executions.order_type,
  executions.channel,
  executions.account_type,
  executions.venue,
  instruments.asset_class,
  instruments.sector,
  executions.execution_currency,

  -- Measures, all additive
  executions.execution_quantity,
  executions.signed_quantity,
  executions.execution_price,
  executions.gross_notional,
  executions.gross_notional_reporting,
  executions.commission,
  executions.commission_reporting,
  executions.signed_cash_flow_reporting,
  executions.fx_rate_to_reporting,

  -- Execution quality. Slippage against the session close is the standard
  -- retail benchmark: negative is a better price than the close for a buy.
  CAST(
    CASE
      WHEN executions.side = 'buy'
        THEN executions.execution_price - daily_prices.close_price
      ELSE daily_prices.close_price - executions.execution_price
    END AS DECIMAL(18, 4)
  ) AS slippage_vs_close,
  CAST(
    executions.commission_reporting
    / NULLIF(executions.gross_notional_reporting, 0) AS DECIMAL(12, 8)
  ) AS commission_rate,

  -- Timestamps
  executions.order_placed_at,
  executions.executed_at,
  DATE_DIFF('second', executions.order_placed_at, executions.executed_at)
    AS seconds_from_order_to_fill,
  HOUR(executions.executed_at) AS execution_hour,
FROM executions
INNER JOIN accounts ON executions.account_id = accounts.account_id
INNER JOIN instruments ON executions.instrument_id = instruments.instrument_id
LEFT JOIN daily_prices
  ON executions.instrument_id = daily_prices.instrument_id
  AND executions.executed_date = daily_prices.price_date
ASOF LEFT JOIN customer_versions
  ON executions.customer_id = customer_versions.customer_id
  AND customer_versions.valid_from <= executions.executed_date
