/*
  Cash in and out of an account: deposits, withdrawals, fees, interest,
  dividends.

  Amounts keep the source's sign convention -- withdrawals and fees arrive
  negative -- so that a plain SUM over the column is the net cash flow. A
  separate `direction` column is derived for anyone who wants to aggregate
  inflow and outflow independently without re-deriving the sign rule.
*/

WITH source AS (

  SELECT * FROM {{ source('landing', 'cash_movements') }}

),

renamed AS (

  SELECT
    movement_id,
    account_id,
    movement_type,
    payment_method,
    CAST(amount AS DECIMAL(18, 2)) AS amount,
    ABS(CAST(amount AS DECIMAL(18, 2))) AS absolute_amount,
    CASE WHEN amount >= 0 THEN 'inflow' ELSE 'outflow' END AS direction,
    currency AS movement_currency,
    CAST(occurred_at AS TIMESTAMP) AS occurred_at,
    CAST(occurred_date AS DATE) AS occurred_date,
    CAST(ingested_at AS TIMESTAMP) AS _ingested_at,
    CAST('{{ run_started_at }}' AS TIMESTAMP) AS _dbt_loaded_at,
    '{{ invocation_id }}' AS _dbt_invocation_id,
  FROM source

)

SELECT * FROM renamed
