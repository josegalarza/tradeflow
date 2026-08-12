/*
  One row per order, at its terminal state.

  Deliberately NOT deduplicated and NOT filtered.

  The reference tables above collapse re-extracted rows because a second copy of
  an instrument is unambiguously noise. An unexpected second copy of an *order*
  is not noise -- it is a defect, and quietly dropping it here would mean the
  data quality tests pass while the pipeline is broken. Staging stays faithful;
  `int_orders_screened` decides what to quarantine, and it does so with a
  recorded reason.
*/

WITH source AS (

  SELECT * FROM {{ source('landing', 'orders') }}

),

renamed AS (

  SELECT
    order_id,
    account_id,
    instrument_id,
    side,
    order_type,
    time_in_force,
    order_status,
    channel,
    CAST(quantity AS DECIMAL(28, 8)) AS order_quantity,
    CAST(limit_price AS DECIMAL(18, 4)) AS limit_price,
    CAST(placed_at AS TIMESTAMP) AS placed_at,
    CAST(resolved_at AS TIMESTAMP) AS resolved_at,
    CAST(placed_date AS DATE) AS placed_date,
    CAST(ingested_at AS TIMESTAMP) AS _ingested_at,
    CAST('{{ run_started_at }}' AS TIMESTAMP) AS _dbt_loaded_at,
    '{{ invocation_id }}' AS _dbt_invocation_id,
  FROM source

)

SELECT * FROM renamed
