/*
  Every fill, with a verdict attached.

  The over-fill check is cumulative rather than aggregate: it walks a fill at a
  time and flags only the fills that push the order past the quantity that was
  requested. Rejecting the whole order would throw away legitimate fills that
  arrived before the bad one, and quietly understate the customer's position --
  a worse outcome than the defect being corrected.

  Fills against a cancelled or rejected order are flagged rather than dropped,
  because that combination usually means the ingestion of the order status and
  the ingestion of the fill disagree, and someone needs to know which one lied.
*/

{{ config(materialized = 'table') }}

WITH executions AS (

  SELECT * FROM {{ ref('stg_executions') }}

),

orders AS (

  SELECT
    order_id,
    order_quantity,
    order_status,
    placed_at,
  FROM {{ ref('int_orders_screened') }}
  WHERE is_valid

),

joined AS (

  SELECT
    executions.*,
    orders.order_quantity,
    orders.order_status,
    orders.placed_at AS order_placed_at,
    COUNT(*) OVER (PARTITION BY executions.execution_id) AS _execution_id_occurrences,
    SUM(executions.execution_quantity) OVER (
      PARTITION BY executions.order_id
      ORDER BY executions.executed_at, executions.execution_id
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_filled_quantity,
  FROM executions
  LEFT JOIN orders ON executions.order_id = orders.order_id

),

with_reasons AS (

  SELECT
    * EXCLUDE (_execution_id_occurrences),
    LIST_FILTER(
      [
        CASE WHEN _execution_id_occurrences > 1
          THEN 'duplicate_execution_id' END,
        CASE WHEN order_quantity IS NULL THEN 'orphan_order' END,
        CASE WHEN executed_at < order_placed_at
          THEN 'executed_before_order_placed' END,
        -- A tolerance, not an equality: quantities are DECIMAL(28,8) and a
        -- fractional crypto fill split across rows can miss by a dust amount
        -- that is arithmetic, not a defect.
        CASE WHEN cumulative_filled_quantity > order_quantity + 0.00000001
          THEN 'over_filled_order' END,
        CASE WHEN order_status IN ('cancelled', 'rejected')
          THEN 'fill_against_terminal_order' END
      ],
      reason -> reason IS NOT NULL
    ) AS dq_reject_reasons,
  FROM joined

)

SELECT
  *,
  LEN(dq_reject_reasons) = 0 AS is_valid,
  dq_reject_reasons[1] AS dq_reject_reason,
FROM with_reasons
