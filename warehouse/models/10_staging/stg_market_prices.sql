/*
  Daily OHLCV per instrument.

  `previous_close_price` comes from the source rather than a LAG here on
  purpose: it is the previous *session's* close, and a LAG over a table where
  equities skip weekends and crypto does not would need a per-asset-class
  window to get right. Derived return measures belong in intermediate.
*/

WITH source AS (

  SELECT * FROM {{ source('landing', 'market_prices') }}

),

renamed AS (

  SELECT
    instrument_id,
    symbol,
    CAST(price_date AS DATE) AS price_date,
    CAST(open_price AS DECIMAL(18, 4)) AS open_price,
    CAST(high_price AS DECIMAL(18, 4)) AS high_price,
    CAST(low_price AS DECIMAL(18, 4)) AS low_price,
    CAST(close_price AS DECIMAL(18, 4)) AS close_price,
    CAST(previous_close_price AS DECIMAL(18, 4)) AS previous_close_price,
    CAST(volume AS BIGINT) AS volume,
    currency AS price_currency,
    CAST(ingested_at AS TIMESTAMP) AS _ingested_at,
    CAST('{{ run_started_at }}' AS TIMESTAMP) AS _dbt_loaded_at,
    '{{ invocation_id }}' AS _dbt_invocation_id,
  FROM source
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY instrument_id, price_date ORDER BY ingested_at DESC
  ) = 1

)

SELECT * FROM renamed
