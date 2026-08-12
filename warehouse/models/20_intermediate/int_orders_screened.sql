/*
  Every order, with a verdict attached.

  This is the quarantine boundary. Staging is faithful to the source, marts are
  built only from rows that pass, and this model is where the decision is made
  and -- critically -- recorded. Nothing is deleted: a rejected order stays
  queryable with the reasons it failed, so "row counts dropped by 0.1% last
  Tuesday" is an answerable question rather than an archaeology project.

  All failing reasons are collected, not just the first. An order can be both
  an orphan and negative, and a triage queue that reveals one defect per pass
  wastes a day per defect.
*/

{{ config(materialized = 'table') }}

WITH orders AS (

  SELECT * FROM {{ ref('stg_orders') }}

),

accounts AS (

  SELECT account_id FROM {{ ref('stg_accounts') }}

),

instruments AS (

  SELECT instrument_id FROM {{ ref('stg_instruments') }}

),

screened AS (

  SELECT
    orders.*,
    COUNT(*) OVER (PARTITION BY orders.order_id) AS _order_id_occurrences,
    accounts.account_id IS NULL AS _is_orphan_account,
    instruments.instrument_id IS NULL AS _is_unknown_instrument,
  FROM orders
  LEFT JOIN accounts ON orders.account_id = accounts.account_id
  LEFT JOIN instruments ON orders.instrument_id = instruments.instrument_id

),

with_reasons AS (

  SELECT
    * EXCLUDE (
      _order_id_occurrences, _is_orphan_account, _is_unknown_instrument
    ),
    -- A NULL entry means "this check passed"; list_filter drops them, leaving
    -- only genuine failures.
    LIST_FILTER(
      [
        CASE WHEN _order_id_occurrences > 1 THEN 'duplicate_order_id' END,
        CASE WHEN _is_orphan_account THEN 'orphan_account' END,
        CASE WHEN _is_unknown_instrument THEN 'unknown_instrument' END,
        CASE WHEN order_quantity IS NULL OR order_quantity <= 0
          THEN 'non_positive_quantity' END,
        CASE WHEN resolved_at < placed_at THEN 'resolved_before_placed' END,
        CASE WHEN placed_at > CURRENT_TIMESTAMP THEN 'placed_in_future' END
      ],
      reason -> reason IS NOT NULL
    ) AS dq_reject_reasons,
  FROM screened

)

SELECT
  *,
  LEN(dq_reject_reasons) = 0 AS is_valid,
  -- Primary reason, for grouping in the observability dashboard where a list
  -- column is awkward to chart.
  dq_reject_reasons[1] AS dq_reject_reason,
FROM with_reasons
