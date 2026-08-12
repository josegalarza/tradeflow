/*
  Daily FX rate per currency pair against the reporting currency.

  Includes the identity row (USD -> USD at 1.0) so every downstream conversion
  is a plain join. Special-casing the reporting currency in each consumer is how
  you end up with three subtly different definitions of revenue.
*/

WITH source AS (

  SELECT * FROM {{ source('landing', 'fx_rates') }}

),

renamed AS (

  SELECT
    base_currency,
    quote_currency,
    CAST(rate_date AS DATE) AS rate_date,
    CAST(rate AS DECIMAL(18, 8)) AS rate,
    CAST(ingested_at AS TIMESTAMP) AS _ingested_at,
    CAST('{{ run_started_at }}' AS TIMESTAMP) AS _dbt_loaded_at,
    '{{ invocation_id }}' AS _dbt_invocation_id,
  FROM source
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY base_currency, quote_currency, rate_date ORDER BY ingested_at DESC
  ) = 1

)

SELECT * FROM renamed
