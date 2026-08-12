/*
  Month-end extracts of the mutable customer record: one row per customer per
  extract date, holding that customer's state as at that date.

  Nothing is masked here. Staging is the faithful, fully-classified copy of the
  source; masking happens in the 40_secure layer, generated from the
  classification tags on these columns. Masking early would mean the warehouse
  could never answer a legitimate compliance question, and would put the
  governance logic in nine different models instead of one generator.
*/

WITH source AS (

  SELECT * FROM {{ source('landing', 'customer_extracts') }}

),

renamed AS (

  SELECT
    customer_id,
    CAST(extract_date AS DATE) AS extract_date,

    -- Identity and contact
    first_name,
    last_name,
    first_name || ' ' || last_name AS full_name,
    LOWER(TRIM(email)) AS email,
    phone_number,
    CAST(date_of_birth AS DATE) AS date_of_birth,
    national_id,

    -- Location
    street_address,
    city,
    postcode,
    country_code,

    -- Commercial and compliance attributes: the ones that actually change, and
    -- therefore the ones SCD2 exists to track.
    kyc_status,
    risk_rating,
    customer_tier,
    marketing_opt_in,

    CAST(created_at AS TIMESTAMP) AS created_at,
    CAST(updated_at AS TIMESTAMP) AS updated_at,
    CAST(ingested_at AS TIMESTAMP) AS _ingested_at,
    CAST('{{ run_started_at }}' AS TIMESTAMP) AS _dbt_loaded_at,
    '{{ invocation_id }}' AS _dbt_invocation_id,
  FROM source
  -- One row per customer per extract: a re-delivered extract file must not
  -- double every customer's history.
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY customer_id, extract_date ORDER BY ingested_at DESC
  ) = 1

)

SELECT * FROM renamed
