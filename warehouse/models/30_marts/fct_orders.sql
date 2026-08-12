/*
  Accumulating snapshot fact. One row per order, updated as the order moves
  through its lifecycle.

  This is the grain most often modelled wrongly as a transaction fact. An order
  is not an event -- it is a process with milestones (placed, first fill, last
  fill, resolved), and the interesting measures are the *lags between* those
  milestones: how long until it started filling, how long until it finished, how
  much of it filled at all. Storing one row per order and updating it in place
  is what makes "median time to first fill by channel" a column scan instead of
  a self-join.

  Cancelled and rejected orders are kept, with zero fills. They are the
  numerator of the cancellation rate, and dropping them would make fill rate a
  meaningless 100%.
*/

WITH orders AS (

  SELECT * FROM {{ ref('int_orders_screened') }}
  WHERE is_valid

),

fills AS (

  SELECT * FROM {{ ref('int_order_fills') }}

),

accounts AS (

  SELECT
    account_key,
    account_id,
    customer_id,
    account_type,
  FROM {{ ref('dim_account') }}

),

customer_versions AS (

  SELECT
    customer_key,
    customer_id,
    valid_from,
  FROM {{ ref('dim_customer') }}

),

instruments AS (

  SELECT
    instrument_key,
    instrument_id,
    symbol,
    asset_class,
    sector,
  FROM {{ ref('dim_instrument') }}

),

joined AS (

  SELECT
    orders.order_id,

    accounts.account_key,
    customer_versions.customer_key,
    instruments.instrument_key,
    orders.placed_date AS date_day,

    orders.account_id,
    accounts.customer_id,
    orders.instrument_id,
    instruments.symbol,

    orders.side,
    orders.order_type,
    orders.time_in_force,
    orders.order_status,
    orders.channel,
    accounts.account_type,
    instruments.asset_class,
    instruments.sector,

    -- Milestones. NULL until the order reaches that stage, which is exactly how
    -- an accumulating snapshot signals "not there yet".
    orders.placed_at,
    fills.first_filled_at,
    fills.last_filled_at,
    orders.resolved_at,

    -- Measures
    orders.order_quantity,
    COALESCE(fills.filled_quantity, 0) AS filled_quantity,
    orders.order_quantity - COALESCE(fills.filled_quantity, 0)
      AS unfilled_quantity,
    COALESCE(fills.fill_count, 0) AS fill_count,
    COALESCE(fills.venue_count, 0) AS venue_count,
    COALESCE(fills.filled_notional_reporting, 0) AS filled_notional_reporting,
    COALESCE(fills.commission_reporting, 0) AS commission_reporting,
    fills.average_fill_price,
    fills.primary_venue,
    orders.limit_price,

    -- Lag measures: the reason this grain exists.
    DATE_DIFF('second', orders.placed_at, fills.first_filled_at)
      AS seconds_to_first_fill,
    DATE_DIFF('second', orders.placed_at, fills.last_filled_at)
      AS seconds_to_last_fill,
    DATE_DIFF('second', orders.placed_at, orders.resolved_at)
      AS seconds_to_resolution,

    -- Flags, as booleans rather than 1/0 integers. COUNT_IF and SUM both work
    -- on a boolean in DuckDB, and a boolean cannot be accidentally averaged
    -- into a meaningless decimal.
    orders.order_status IN ('filled', 'partially_filled') AS is_filled_any,
    orders.order_status = 'filled' AS is_fully_filled,
    orders.order_status = 'cancelled' AS is_cancelled,
    orders.order_status = 'rejected' AS is_rejected,
    HOUR(orders.placed_at) AS placed_hour,
  FROM orders
  LEFT JOIN fills ON orders.order_id = fills.order_id
  INNER JOIN accounts ON orders.account_id = accounts.account_id
  INNER JOIN instruments ON orders.instrument_id = instruments.instrument_id
  ASOF LEFT JOIN customer_versions
    ON accounts.customer_id = customer_versions.customer_id
    AND customer_versions.valid_from <= orders.placed_date

)

SELECT
  *,
  CAST(
    filled_quantity / NULLIF(order_quantity, 0) AS DECIMAL(9, 6)
  ) AS fill_rate,
  -- Price improvement against the limit the customer set. Only meaningful when
  -- there was a limit and it actually filled.
  CASE
    WHEN limit_price IS NULL OR average_fill_price IS NULL THEN NULL
    WHEN side = 'buy' THEN limit_price - average_fill_price
    ELSE average_fill_price - limit_price
  END AS price_improvement_vs_limit,
FROM joined
