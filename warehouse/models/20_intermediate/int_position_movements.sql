/*
  Net daily change in holdings and cash per account and instrument.

  Collapsing fills to one row per (account, instrument, day) before the running
  balance is what keeps `fct_positions_daily` affordable. Running a window
  function over every individual fill and then sampling it daily would do the
  same arithmetic several times per day per position, for an identical answer.
*/

WITH fills AS (

  SELECT * FROM {{ ref('int_executions_priced') }}

)

SELECT
  account_id,
  instrument_id,
  executed_date AS activity_date,
  SUM(signed_quantity) AS net_quantity_change,
  SUM(signed_cash_flow_reporting) AS net_trade_cash_flow_reporting,
  SUM(commission_reporting) AS commission_reporting,
  SUM(CASE WHEN side = 'buy' THEN execution_quantity ELSE 0 END) AS bought_quantity,
  SUM(CASE WHEN side = 'sell' THEN execution_quantity ELSE 0 END) AS sold_quantity,
  -- Cost of the day's purchases, used to carry a weighted-average cost basis
  -- forward in the daily snapshot.
  SUM(
    CASE WHEN side = 'buy' THEN gross_notional_reporting ELSE 0 END
  ) AS bought_cost_reporting,
  SUM(
    CASE WHEN side = 'sell' THEN gross_notional_reporting ELSE 0 END
  ) AS sold_proceeds_reporting,
  COUNT(*) AS fill_count,
FROM fills
GROUP BY
  account_id,
  instrument_id,
  executed_date
