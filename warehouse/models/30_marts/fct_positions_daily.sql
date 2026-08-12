/*
  Periodic snapshot fact. One row per account, instrument and day on which a
  position was actually held.

  Three decisions carry this model.

  *Only days with a non-zero holding exist.* The naive spine -- accounts x
  instruments x days -- is a cross join that grows without limit and is
  overwhelmingly empty; nobody holds every instrument every day. Instead the
  running balance is computed at the dates it actually changes, each balance is
  turned into the interval it stayed valid for, and only those intervals are
  expanded to daily rows. Cost becomes proportional to real position-days.

  *A trailing hot window, kept incrementally.* Full daily history for every
  position is the natural extension but multiplies rows by the length of the
  dataset for a chart nobody scrolls back through. `positions_snapshot_days`
  bounds the window; the incremental build then reprocesses a short lookback
  (catching late-arriving fills) and appends new days, so history accumulates
  across runs rather than being rebuilt each time. See docs/adr/0005.

  *ASOF JOIN for the mark-to-market price.* A position exists every day it is
  held, including weekends and holidays, but equities are only priced on trading
  days. An equi-join on date silently produces a NULL market value for a third
  of the rows -- and a NULL that SUMs to an understated portfolio. ASOF JOIN
  takes the most recent price at or before the snapshot date, which is what
  "the position was worth this on Sunday" actually means.

  On cost basis: `net_invested_reporting` is cumulative purchase cost less
  cumulative sale proceeds -- net capital deployed, not a weighted-average cost
  basis. True average-cost accounting requires reducing the basis
  proportionally on every sale, which is inherently sequential and would need a
  recursive CTE. It is deliberately out of scope, and the column is named for
  what it is rather than for what it might be mistaken for, so that
  `unrealised_gain_reporting` below is honestly "gain against capital
  deployed".
*/

{{
  config(
    materialized = 'incremental',
    unique_key = ['account_id', 'instrument_id', 'snapshot_date'],
    incremental_strategy = 'delete+insert',
  )
}}

WITH bounds AS (

  SELECT
    MAX(date_day) AS max_date,
    {% if is_incremental() %}
      -- Reprocess a short lookback so a fill that arrived late still corrects
      -- the days it belongs to, then append everything newer.
      (SELECT MAX(snapshot_date) FROM {{ this }})
        - INTERVAL '{{ var("positions_lookback_days", 3) }}' DAY
    {% else %}
      MAX(date_day) - INTERVAL '{{ var("positions_snapshot_days") }}' DAY
    {% endif %} AS window_start,
  FROM {{ ref('dim_date') }}

),

movements AS (

  SELECT * FROM {{ ref('int_position_movements') }}

),

running_balance AS (

  SELECT
    account_id,
    instrument_id,
    activity_date,
    SUM(net_quantity_change) OVER position_to_date AS position_quantity,
    SUM(bought_cost_reporting - sold_proceeds_reporting) OVER position_to_date
      AS net_invested_reporting,
    SUM(commission_reporting) OVER position_to_date
      AS cumulative_commission_reporting,
    SUM(net_trade_cash_flow_reporting) OVER position_to_date
      AS cumulative_trade_cash_flow_reporting,
    LEAD(activity_date) OVER (
      PARTITION BY account_id, instrument_id ORDER BY activity_date
    ) AS next_activity_date,
  FROM movements
  WINDOW position_to_date AS (
    PARTITION BY account_id, instrument_id
    ORDER BY activity_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
  )

),

held_intervals AS (

  SELECT
    running_balance.*,
    activity_date AS held_from,
    COALESCE(
      next_activity_date - INTERVAL 1 DAY, bounds.max_date
    ) AS held_to,
    bounds.max_date,
    CAST(bounds.window_start AS DATE) AS window_start,
  FROM running_balance
  CROSS JOIN bounds
  -- A balance that has gone to zero is not a position. The tolerance absorbs
  -- decimal dust from fractional crypto fills that net to "nothing left".
  WHERE running_balance.position_quantity > 0.00000001

),

clipped AS (

  -- Clip to the window *before* expanding. Expanding first and filtering after
  -- would generate every historical day only to throw it away.
  SELECT
    *,
    GREATEST(held_from, window_start) AS expand_from,
    LEAST(held_to, max_date) AS expand_to,
  FROM held_intervals
  WHERE held_to >= window_start
    AND held_from <= max_date

),

expanded AS (

  SELECT
    * EXCLUDE (expand_from, expand_to),
    CAST(UNNEST(
      GENERATE_SERIES(expand_from, expand_to, INTERVAL 1 DAY)
    ) AS DATE) AS snapshot_date,
  FROM clipped

),

prices AS (

  SELECT
    instrument_id,
    price_date,
    close_price,
  FROM {{ ref('stg_market_prices') }}

),

fx AS (

  SELECT
    base_currency,
    rate_date,
    rate,
  FROM {{ ref('stg_fx_rates') }}
  WHERE quote_currency = '{{ var("reporting_currency") }}'

),

valued AS (

  SELECT
    expanded.account_id,
    expanded.instrument_id,
    expanded.snapshot_date,
    expanded.position_quantity,
    expanded.net_invested_reporting,
    expanded.cumulative_commission_reporting,
    expanded.cumulative_trade_cash_flow_reporting,
    expanded.activity_date AS last_activity_date,
    prices.close_price AS mark_price,
    prices.price_date AS mark_price_date,
    fx.rate AS fx_rate_to_reporting,
  FROM expanded
  ASOF LEFT JOIN prices
    ON expanded.instrument_id = prices.instrument_id
    AND prices.price_date <= expanded.snapshot_date
  LEFT JOIN {{ ref('stg_instruments') }} AS instruments
    ON expanded.instrument_id = instruments.instrument_id
  -- ASOF for the same reason as the price join, and it was originally an
  -- equi-join for the same wrong reason. The window can extend one day past the
  -- last published rate -- dim_date spans all observed activity, and a fill can be
  -- timestamped after the final session -- which left market_value_reporting NULL
  -- for those rows and understated the whole platform's holdings.
  ASOF LEFT JOIN fx
    ON instruments.listing_currency = fx.base_currency
    AND fx.rate_date <= expanded.snapshot_date

)

SELECT
  valued.account_id,
  valued.instrument_id,
  valued.snapshot_date,
  accounts.account_key,
  instruments.instrument_key,
  accounts.customer_id,
  instruments.symbol,
  instruments.asset_class,
  instruments.sector,

  valued.position_quantity,
  valued.mark_price,
  valued.mark_price_date,
  valued.snapshot_date <> valued.mark_price_date AS is_stale_price,
  valued.fx_rate_to_reporting,

  CAST(
    valued.position_quantity * valued.mark_price * valued.fx_rate_to_reporting
    AS DECIMAL(18, 4)
  ) AS market_value_reporting,
  CAST(valued.net_invested_reporting AS DECIMAL(18, 4)) AS net_invested_reporting,
  CAST(
    valued.position_quantity * valued.mark_price * valued.fx_rate_to_reporting
    - valued.net_invested_reporting AS DECIMAL(18, 4)
  ) AS unrealised_gain_reporting,
  CAST(valued.cumulative_commission_reporting AS DECIMAL(18, 4))
    AS cumulative_commission_reporting,
  DATEDIFF('day', valued.last_activity_date, valued.snapshot_date)
    AS days_since_last_trade,
FROM valued
INNER JOIN {{ ref('dim_account') }} AS accounts
  ON valued.account_id = accounts.account_id
INNER JOIN {{ ref('dim_instrument') }} AS instruments
  ON valued.instrument_id = instruments.instrument_id
