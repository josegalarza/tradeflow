/*
  One row per brokerage account.

  `account_status` is recomputed from `closed_at` rather than trusted from the
  source. The source carries both, and when a denormalised status flag and the
  timestamp it summarises disagree, the timestamp is the fact and the flag is an
  opinion.
*/

WITH source AS (

  SELECT * FROM {{ source('landing', 'accounts') }}

),

renamed AS (

  SELECT
    account_id,
    customer_id,
    account_type,
    base_currency,
    CAST(opened_at AS TIMESTAMP) AS opened_at,
    CAST(closed_at AS TIMESTAMP) AS closed_at,
    CAST(opened_at AS DATE) AS opened_date,
    CAST(closed_at AS DATE) AS closed_date,
    CASE WHEN closed_at IS NULL THEN 'open' ELSE 'closed' END AS account_status,
    CAST(margin_limit AS DECIMAL(18, 2)) AS margin_limit,
    CAST(ingested_at AS TIMESTAMP) AS _ingested_at,
    CAST('{{ run_started_at }}' AS TIMESTAMP) AS _dbt_loaded_at,
    '{{ invocation_id }}' AS _dbt_invocation_id,
  FROM source
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY account_id ORDER BY ingested_at DESC
  ) = 1

)

SELECT * FROM renamed
