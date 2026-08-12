/*
  One row per fill. Many per order; none for cancelled or rejected orders.

  Faithful to the source for the same reason as `stg_orders`: a duplicated fill
  is the single most expensive defect this domain can produce -- it overstates a
  customer's holdings -- so it must reach a screen that reports it, not a
  DISTINCT that hides it.
*/

WITH source AS (

  SELECT * FROM {{ source('landing', 'executions') }}

),

renamed AS (

  SELECT
    execution_id,
    order_id,
    venue,
    CAST(quantity AS DECIMAL(28, 8)) AS execution_quantity,
    CAST(execution_price AS DECIMAL(18, 4)) AS execution_price,
    currency AS execution_currency,
    CAST(commission AS DECIMAL(18, 4)) AS commission,
    -- Gross of commission, in the instrument's listing currency. Converted to
    -- the reporting currency in int_executions_priced, where the FX join lives.
    CAST(quantity AS DECIMAL(28, 8))
      * CAST(execution_price AS DECIMAL(18, 4)) AS gross_notional,
    CAST(executed_at AS TIMESTAMP) AS executed_at,
    CAST(executed_date AS DATE) AS executed_date,
    CAST(ingested_at AS TIMESTAMP) AS _ingested_at,
    CAST('{{ run_started_at }}' AS TIMESTAMP) AS _dbt_loaded_at,
    '{{ invocation_id }}' AS _dbt_invocation_id,
  FROM source

)

SELECT * FROM renamed
