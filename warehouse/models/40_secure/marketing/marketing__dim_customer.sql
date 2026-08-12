{#
  GENERATED FILE -- DO NOT EDIT.

  Written by governance/generate_secure_views.py from the classification tags in
  the dbt schema YAML and the role definitions in governance/policy.yml.

  To change what this role can see, edit the policy or the column's tags and run
  `make governance`. Editing this file directly will be reverted by the next
  generation, and CI checks that it matches.
#}

/*
  dim_customer as seen by the `marketing` role.

  Role clearance : internal
  Source model   : marts.dim_customer
  Columns        : 18 exposed, 0 masked, 13 withheld

  Withheld entirely (above clearance, and this role omits
  rather than masks -- a masked column still advertises that
  the data exists):
    first_name (confidential)
    last_name (confidential)
    full_name (confidential)
    email (restricted)
    phone_number (restricted)
    national_id (restricted)
    date_of_birth (restricted)
    street_address (restricted)
    city (confidential)
    postcode (confidential)
    kyc_status (confidential)
    risk_rating (confidential)
    age_years (confidential)
*/

{{
  config(
    schema = 'secure_marketing',
    materialized = 'view',
    tags = ['secure', 'governance', 'role:marketing'],
  )
}}

SELECT
  customer_key,
  customer_id,
  version_number,
  valid_from,
  valid_to,
  is_current,
  country_code,
  customer_tier,
  marketing_opt_in,
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
