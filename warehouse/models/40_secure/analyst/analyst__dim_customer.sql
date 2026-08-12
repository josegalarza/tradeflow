{#
  GENERATED FILE -- DO NOT EDIT.

  Written by governance/generate_secure_views.py from the classification tags in
  the dbt schema YAML and the role definitions in governance/policy.yml.

  To change what this role can see, edit the policy or the column's tags and run
  `make governance`. Editing this file directly will be reverted by the next
  generation, and CI checks that it matches.
#}

/*
  dim_customer as seen by the `analyst` role.

  Role clearance : internal
  Source model   : marts.dim_customer
  Columns        : 31 exposed, 10 masked, 0 withheld

  Masked:
    first_name                         redact
    last_name                          redact
    full_name                          redact
    email                              hash
    phone_number                       partial
    national_id                        redact
    date_of_birth                      generalize
    street_address                     redact
    postcode                           generalize
    age_years                          redact
*/

{{
  config(
    schema = 'secure_analyst',
    materialized = 'view',
    tags = ['secure', 'governance', 'role:analyst'],
  )
}}

SELECT
  customer_key,
  customer_id,
  version_number,
  valid_from,
  valid_to,
  is_current,
  {{ mask_redact('first_name', 'VARCHAR') }} AS first_name,
  {{ mask_redact('last_name', 'VARCHAR') }} AS last_name,
  {{ mask_redact('full_name', 'VARCHAR') }} AS full_name,
  {{ mask_hash('email') }} AS email,
  {{ mask_partial_phone('phone_number') }} AS phone_number,
  {{ mask_redact('national_id', 'VARCHAR') }} AS national_id,
  {{ mask_generalize_date('date_of_birth') }} AS date_of_birth,
  {{ mask_redact('street_address', 'VARCHAR') }} AS street_address,
  city,
  {{ mask_generalize_postcode('postcode') }} AS postcode,
  country_code,
  kyc_status,
  risk_rating,
  customer_tier,
  marketing_opt_in,
  {{ mask_redact('age_years', 'BIGINT') }} AS age_years,
  age_band,
  tenure_days_at_version,
  observed_at_extract_date,
  attribute_hash,
  signup_date,
  signup_month,
  is_kyc_verified,
  created_at,
  updated_at,
FROM {{ ref('dim_customer') }}
