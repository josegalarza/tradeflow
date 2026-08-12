/*
  Clickstream events, grouped into sessions. The highest-volume table.

  Two columns here decide whether this project's governance layer is real:
  `ip_address` and `user_agent`. Neither has a name that looks like personal
  data, both are personal data, and both are the columns a classification
  exercise driven by name-matching will miss. They are classified as
  confidential online identifiers and masked for every role except `auditor`.

  `ip_address` is also kept in a truncated form: the /24 prefix is enough for
  geography and fraud-adjacent analysis, and it is the value analysts should
  reach for by default.
*/

WITH source AS (

  SELECT * FROM {{ source('landing', 'app_events') }}

),

renamed AS (

  SELECT
    event_id,
    session_id,
    customer_id,
    event_type,
    device_family,
    app_version,
    user_agent,
    ip_address,
    -- Coarse network location. Retains analytical value, loses the ability to
    -- single out a household.
    REGEXP_REPLACE(ip_address, '\.\d+$', '.0') AS ip_address_prefix,
    CAST(occurred_at AS TIMESTAMP) AS occurred_at,
    CAST(event_date AS DATE) AS event_date,
    CAST(ingested_at AS TIMESTAMP) AS _ingested_at,
    CAST('{{ run_started_at }}' AS TIMESTAMP) AS _dbt_loaded_at,
    '{{ invocation_id }}' AS _dbt_invocation_id,
  FROM source

)

SELECT * FROM renamed
