{#
  GENERATED FILE -- DO NOT EDIT.

  Written by governance/generate_secure_views.py from the classification tags in
  the dbt schema YAML and the role definitions in governance/policy.yml.

  To change what this role can see, edit the policy or the column's tags and run
  `make governance`. Editing this file directly will be reverted by the next
  generation, and CI checks that it matches.
#}

/*
  dim_customer as seen by the `auditor` role.

  Role clearance : restricted
  Source model   : marts.dim_customer
  Columns        : 31 exposed, 0 masked, 0 withheld
*/

{{
  config(
    schema = 'secure_auditor',
    materialized = 'view',
    tags = ['secure', 'governance', 'role:auditor'],
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
  email,
  phone_number,
  national_id,
  date_of_birth,
  street_address,
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
