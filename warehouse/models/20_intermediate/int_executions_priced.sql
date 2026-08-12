/*
  Valid fills, resolved to the reporting currency and joined to their trading
  context.

  Two things happen here that must happen exactly once in the warehouse:

  1. FX conversion. Every downstream model consumes the reporting-currency
     amounts from this model rather than converting for itself. Three consumers
     each doing their own conversion is three subtly different definitions of
     revenue, and the reconciliation meeting that follows.

  2. Sign convention. A buy removes cash and adds quantity; a sell does the
     reverse. Encoding that here means the position and cash-balance models are
     plain running sums, and neither has to remember which way round a sell
     goes.
*/

{{ config(materialized = 'table') }}

WITH executions AS (

  SELECT * FROM {{ ref('int_executions_screened') }}
  WHERE is_valid

),

orders AS (

  SELECT
    order_id,
    account_id,
    instrument_id,
    side,
    order_type,
    channel,
    placed_at,
  FROM {{ ref('int_orders_screened') }}
  WHERE is_valid

),

accounts AS (

  SELECT
    account_id,
    customer_id,
    account_type,
    base_currency,
  FROM {{ ref('stg_accounts') }}

),

fx_rates AS (

  SELECT
    base_currency,
    rate_date,
    rate,
  FROM {{ ref('stg_fx_rates') }}
  WHERE quote_currency = '{{ var("reporting_currency", "USD") }}'

),

joined AS (

  SELECT
    executions.execution_id,
    executions.order_id,
    orders.account_id,
    accounts.customer_id,
    orders.instrument_id,
    orders.side,
    orders.order_type,
    orders.channel,
    accounts.account_type,
    executions.venue,
    executions.executed_at,
    executions.executed_date,
    orders.placed_at AS order_placed_at,
    executions.execution_quantity,
    executions.execution_price,
    executions.execution_currency,
    executions.commission,
    executions.gross_notional,
    fx_rates.rate AS fx_rate_to_reporting,
  FROM executions
  INNER JOIN orders ON executions.order_id = orders.order_id
  INNER JOIN accounts ON orders.account_id = accounts.account_id
  -- ASOF: the most recent rate at or before the fill.
  --
  -- This was an equi-join on the date, with a comment claiming that a missing
  -- rate is a real gap which should fail loudly. It did not fail loudly -- being
  -- an INNER join, it silently *dropped* the fill. And a rate can legitimately
  -- be missing: a crypto order placed at 23:59 on the last day of the window
  -- fills after midnight, past the last published rate.
  --
  -- Carrying the last known rate forward is also what a real system does; you
  -- convert at the most recent published rate, not at no rate. The gap-detection
  -- intent is preserved by the not_null test on fx_rate_to_reporting, which
  -- catches a genuinely absent currency instead of hiding it.
  ASOF LEFT JOIN fx_rates
    ON executions.execution_currency = fx_rates.base_currency
    AND fx_rates.rate_date <= executions.executed_date

)

SELECT
  *,
  -- Signed measures. Additive across every dimension, which is what makes the
  -- downstream snapshots a running SUM rather than a CASE expression.
  CASE WHEN side = 'buy'
    THEN execution_quantity
    ELSE -execution_quantity
  END AS signed_quantity,
  CAST(gross_notional * fx_rate_to_reporting AS DECIMAL(18, 4))
    AS gross_notional_reporting,
  CAST(commission * fx_rate_to_reporting AS DECIMAL(18, 4))
    AS commission_reporting,
  CAST(
    CASE WHEN side = 'buy'
      THEN -(gross_notional + commission)
      ELSE gross_notional - commission
    END * fx_rate_to_reporting AS DECIMAL(18, 4)
  ) AS signed_cash_flow_reporting,
FROM joined
