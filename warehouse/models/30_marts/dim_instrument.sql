/*
  Instrument dimension, Type 1. The conformed dimension of this warehouse --
  orders, executions, positions and prices all resolve to this key.

  Latest price attributes are denormalised on: every consumer wants "what is it
  worth now" alongside the descriptive attributes, and the alternative is the
  same correlated lookup written slightly differently in a dozen places.
*/

WITH instruments AS (

  SELECT * FROM {{ ref('stg_instruments') }}

),

latest_price AS (

  SELECT
    instrument_id,
    close_price AS latest_close_price,
    price_date AS latest_price_date,
    previous_close_price AS latest_previous_close_price,
  FROM {{ ref('stg_market_prices') }}
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY instrument_id ORDER BY price_date DESC
  ) = 1

),

price_history AS (

  SELECT
    instrument_id,
    MIN(price_date) AS first_price_date,
    MIN(low_price) AS all_time_low_price,
    MAX(high_price) AS all_time_high_price,
    AVG(volume) AS average_daily_volume,
  FROM {{ ref('stg_market_prices') }}
  GROUP BY instrument_id

)

SELECT
  {{ dbt_utils.generate_surrogate_key(['instruments.instrument_id']) }}
    AS instrument_key,
  instruments.instrument_id,
  instruments.symbol,
  instruments.instrument_name,
  instruments.asset_class,
  instruments.exchange,
  instruments.sector,
  instruments.listing_currency,
  instruments.dividend_yield,
  instruments.is_active,
  instruments.listed_date,

  -- Derived groupings the dashboard filters on.
  instruments.asset_class = 'crypto' AS trades_every_day,
  instruments.listing_currency
    = '{{ var("reporting_currency") }}' AS is_reporting_currency,
  instruments.dividend_yield > 0 AS pays_dividend,

  latest_price.latest_close_price,
  latest_price.latest_price_date,
  CAST(
    (latest_price.latest_close_price - latest_price.latest_previous_close_price)
    / NULLIF(latest_price.latest_previous_close_price, 0) AS DECIMAL(12, 6)
  ) AS latest_daily_return,
  price_history.first_price_date,
  price_history.all_time_low_price,
  price_history.all_time_high_price,
  CAST(price_history.average_daily_volume AS BIGINT) AS average_daily_volume,
FROM instruments
LEFT JOIN latest_price ON instruments.instrument_id = latest_price.instrument_id
LEFT JOIN price_history
  ON instruments.instrument_id = price_history.instrument_id
