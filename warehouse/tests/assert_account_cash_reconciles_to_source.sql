/*
  The strongest test in this warehouse.

  `fct_account_daily.cash_balance_reporting` is built with window functions over
  a date spine, carrying an opening balance into a trailing window. That is
  exactly the kind of SQL that produces plausible, smooth, wrong numbers -- an
  off-by-one in the window frame, a spine row that outlives its account, or an
  opening balance that double-counts the boundary day all yield a chart that
  looks perfectly reasonable.

  So this test ignores the model's own arithmetic entirely and recomputes the
  balance from the atomic sources: cash movements out of staging, plus the cash
  side of every fill. If the two disagree by more than a cent, the snapshot is
  wrong.

  A test that reuses the model's logic to check the model proves only that the
  logic is deterministic.
*/

WITH fx AS (

  SELECT
    base_currency,
    rate_date,
    rate,
  FROM {{ ref('stg_fx_rates') }}
  WHERE quote_currency = '{{ var("reporting_currency") }}'

),

-- Independent path 1: cash in and out, straight from staging.
movement_cash AS (

  SELECT
    movements.account_id,
    movements.occurred_date AS activity_date,
    SUM(movements.amount * fx.rate) AS cash_delta,
  FROM {{ ref('stg_cash_movements') }} AS movements
  ASOF LEFT JOIN fx
    ON movements.movement_currency = fx.base_currency
    AND fx.rate_date <= movements.occurred_date
  GROUP BY 1, 2

),

-- Independent path 2: the cash consequences of trading.
trade_cash AS (

  SELECT
    account_id,
    executed_date AS activity_date,
    SUM(signed_cash_flow_reporting) AS cash_delta,
  FROM {{ ref('int_executions_priced') }}
  GROUP BY 1, 2

),

all_deltas AS (

  SELECT * FROM movement_cash
  UNION ALL
  SELECT * FROM trade_cash

),

expected AS (

  SELECT
    snapshot.account_id,
    snapshot.snapshot_date,
    snapshot.cash_balance_reporting AS actual_cash,
    (
      SELECT COALESCE(SUM(all_deltas.cash_delta), 0)
      FROM all_deltas
      WHERE all_deltas.account_id = snapshot.account_id
        AND all_deltas.activity_date <= snapshot.snapshot_date
    ) AS expected_cash,
  FROM {{ ref('fct_account_daily') }} AS snapshot

)

SELECT
  account_id,
  snapshot_date,
  actual_cash,
  expected_cash,
  actual_cash - expected_cash AS difference,
FROM expected
-- One cent of tolerance for DECIMAL rounding across the FX multiplication.
WHERE ABS(actual_cash - expected_cash) > 0.01
