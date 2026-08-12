{#
  GENERATED FILE -- DO NOT EDIT.

  Written by governance/generate_secure_views.py from the classification tags in
  the dbt schema YAML and the role definitions in governance/policy.yml.

  To change what this role can see, edit the policy or the column's tags and run
  `make governance`. Editing this file directly will be reverted by the next
  generation, and CI checks that it matches.
#}

/*
  dim_customer as seen by the `support` role.

  Role clearance : confidential
  Source model   : marts.dim_customer
  Columns        : 31 exposed, 5 masked, 0 withheld

  Masked:
    email                              partial
    phone_number                       partial
    national_id                        redact
    date_of_birth                      generalize
    street_address                     redact
*/

{{
  config(
    schema = 'secure_support',
    materialized = 'view',
    tags = ['secure', 'governance', 'role:support'],
  )
}}

SELECT
  customer_key,
  customer_id,
  version_number,
  valid_from,
  valid_to,
  is_current,
  first_name,
  last_name,
  full_name,
  {{ mask_partial_email('email') }} AS email,
  {{ mask_partial_phone('phone_number') }} AS phone_number,
  {{ mask_redact('national_id', 'VARCHAR') }} AS national_id,
  {{ mask_generalize_date('date_of_birth') }} AS date_of_birth,
  {{ mask_redact('street_address', 'VARCHAR') }} AS street_address,
  city,
  postcode,
  country_code,
  kyc_status,
  risk_rating,
  customer_tier,
  marketing_opt_in,
  age_years,
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
