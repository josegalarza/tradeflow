/*
  Fill summary per order: how much was delivered, at what average price, and
  when the milestones happened.

  Volume-weighted average price, not a mean of prices. Averaging the price
  column would weight a one-share fill the same as a thousand-share fill, which
  is wrong by an amount that grows with how fragmented the order was -- the
  classic silent error in execution reporting.

  Only orders with at least one valid fill appear here. `fct_orders` LEFT JOINs
  so that cancelled and rejected orders survive with zero fills.
*/

WITH fills AS (

  SELECT * FROM {{ ref('int_executions_priced') }}

),

aggregated AS (

  SELECT
    order_id,
    COUNT(*) AS fill_count,
    COUNT(DISTINCT venue) AS venue_count,
    SUM(execution_quantity) AS filled_quantity,
    SUM(gross_notional) AS filled_notional,
    SUM(gross_notional_reporting) AS filled_notional_reporting,
    SUM(commission_reporting) AS commission_reporting,
    SUM(execution_quantity * execution_price)
      / NULLIF(SUM(execution_quantity), 0) AS volume_weighted_price,
    MIN(executed_at) AS first_filled_at,
    MAX(executed_at) AS last_filled_at,
    MIN(executed_date) AS first_filled_date,
    -- Which venue took the largest share of the order, for routing analysis.
    ARG_MAX(venue, execution_quantity) AS primary_venue,
  FROM fills
  GROUP BY order_id

)

SELECT
  *,
  CAST(volume_weighted_price AS DECIMAL(18, 4)) AS average_fill_price,
FROM aggregated
