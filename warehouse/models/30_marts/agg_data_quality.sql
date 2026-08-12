/*
  Quarantine summary: what was rejected, when, why, and how much it was worth.

  This is the model that turns the screening layer from a filter into an
  observable. Without it, "we drop bad rows" is an unverifiable claim; with it,
  the dashboard has a data quality page, the Slack notifier has something to
  report, and a rejection rate that creeps up over a fortnight is visible rather
  than merely true.

  Rejected rows are counted by *every* reason they failed, not just their
  primary one -- an order that is both an orphan and negative should appear in
  both counts, because a triage queue that shows one defect per row per pass
  costs a day per defect.
*/

WITH order_rejects AS (

  SELECT
    'orders' AS model_name,
    placed_date AS activity_date,
    UNNEST(dq_reject_reasons) AS reject_reason,
    1 AS rejected_rows,
    order_quantity AS affected_quantity,
  FROM {{ ref('int_orders_screened') }}
  WHERE NOT is_valid

),

execution_rejects AS (

  SELECT
    'executions' AS model_name,
    executed_date AS activity_date,
    UNNEST(dq_reject_reasons) AS reject_reason,
    1 AS rejected_rows,
    execution_quantity AS affected_quantity,
  FROM {{ ref('int_executions_screened') }}
  WHERE NOT is_valid

),

all_rejects AS (

  SELECT * FROM order_rejects
  UNION ALL
  SELECT * FROM execution_rejects

),

rejects_by_day AS (

  SELECT
    model_name,
    activity_date,
    reject_reason,
    SUM(rejected_rows) AS rejected_rows,
    SUM(affected_quantity) AS affected_quantity,
  FROM all_rejects
  GROUP BY 1, 2, 3

),

-- Denominators, so a count of rejects can be read as a rate. A raw count rises
-- with volume and tells you nothing about whether quality changed.
totals AS (

  SELECT
    'orders' AS model_name,
    placed_date AS activity_date,
    COUNT(*) AS total_rows,
    COUNT_IF(NOT is_valid) AS total_rejected_rows,
  FROM {{ ref('int_orders_screened') }}
  GROUP BY 1, 2

  UNION ALL

  SELECT
    'executions' AS model_name,
    executed_date AS activity_date,
    COUNT(*) AS total_rows,
    COUNT_IF(NOT is_valid) AS total_rejected_rows,
  FROM {{ ref('int_executions_screened') }}
  GROUP BY 1, 2

)

SELECT
  totals.model_name,
  totals.activity_date,
  COALESCE(rejects_by_day.reject_reason, 'none') AS reject_reason,
  totals.total_rows,
  totals.total_rejected_rows,
  COALESCE(rejects_by_day.rejected_rows, 0) AS rejected_rows,
  COALESCE(rejects_by_day.affected_quantity, 0) AS affected_quantity,
  CAST(
    COALESCE(rejects_by_day.rejected_rows, 0)
    / NULLIF(totals.total_rows, 0) AS DECIMAL(9, 6)
  ) AS reject_rate,
  CAST(
    totals.total_rejected_rows
    / NULLIF(totals.total_rows, 0) AS DECIMAL(9, 6)
  ) AS overall_reject_rate,
FROM totals
LEFT JOIN rejects_by_day
  ON totals.model_name = rejects_by_day.model_name
  AND totals.activity_date = rejects_by_day.activity_date
