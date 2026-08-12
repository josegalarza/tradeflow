/*
  Nothing can happen on an account before it exists.

  This test exists because the violation actually occurred. The generator rolls
  an order placed while the market is shut forward into the next session -- but on
  the final weekend of the data window there is no next session, so it fell back
  to the *previous* one, back-dating a handful of orders to before their account
  was opened. It surfaced as twelve unexplained rows in the cash reconciliation
  test, and took a while to trace.

  A causality invariant is cheap to state and catches a whole family of bugs:
  timezone handling that shifts dates, a backfill that reuses the wrong
  partition, a join that picks the wrong account. Worth one test.
*/

WITH accounts AS (

  SELECT
    account_id,
    opened_date,
    closed_date,
  FROM {{ ref('dim_account') }}

),

activity AS (

  SELECT
    account_id,
    'order' AS activity_type,
    order_id AS activity_id,
    date_day AS activity_date,
  FROM {{ ref('fct_orders') }}

  UNION ALL

  SELECT
    account_id,
    'execution' AS activity_type,
    execution_id AS activity_id,
    date_day AS activity_date,
  FROM {{ ref('fct_executions') }}

  UNION ALL

  SELECT
    account_id,
    'cash_movement' AS activity_type,
    movement_id AS activity_id,
    occurred_date AS activity_date,
  FROM {{ ref('stg_cash_movements') }}

)

SELECT
  activity.account_id,
  activity.activity_type,
  activity.activity_id,
  activity.activity_date,
  accounts.opened_date,
  accounts.closed_date,
FROM activity
INNER JOIN accounts ON activity.account_id = accounts.account_id
WHERE activity.activity_date < accounts.opened_date
