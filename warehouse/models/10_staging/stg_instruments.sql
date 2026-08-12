/*
  Instrument reference data, one row per instrument.

  The generator's simulation parameters (start price, drift, volatility) are
  deliberately dropped here: they are inputs to the fake data, not facts about
  the instrument, and leaking them into the warehouse would invite someone to
  build a chart on top of them.
*/

WITH source AS (

  SELECT * FROM {{ source('landing', 'instruments') }}

),

renamed AS (

  SELECT
    instrument_id,
    symbol,
    instrument_name,
    asset_class,
    exchange,
    sector,
    currency AS listing_currency,
    CAST(dividend_yield AS DECIMAL(9, 6)) AS dividend_yield,
    is_active,
    CAST(listed_date AS DATE) AS listed_date,
    CAST(ingested_at AS TIMESTAMP) AS _ingested_at,
    CAST('{{ run_started_at }}' AS TIMESTAMP) AS _dbt_loaded_at,
    '{{ invocation_id }}' AS _dbt_invocation_id,
  FROM source
  -- Re-extraction of a reference table legitimately produces duplicates; the
  -- newest wins. DuckDB's QUALIFY keeps this to one pass with no subquery.
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY instrument_id ORDER BY ingested_at DESC
  ) = 1

)

SELECT * FROM renamed
