/*
  Customer dimension, Type 2.

  One row per customer per version of their attributes. Facts resolve to the
  version that was current when the event happened, so a trade placed while a
  customer was rated `medium` risk stays attributed to `medium` risk forever,
  even after compliance moves them to `high`. That is the entire point of SCD2,
  and the reason a Type 1 dimension quietly rewrites history every time
  someone's details change.

  `customer_key` is the surrogate: hash of (customer_id, valid_from). Facts
  carry it; nothing joins on customer_id and a date range at query time.

  Derived attributes deliberately use `valid_from` as their reference point, not
  today. `age_years` is the customer's age when the version opened -- an
  as-at-the-time attribute, consistent with everything else on the row. Using
  CURRENT_DATE would make historical rows change on every rebuild, which breaks
  the one promise a Type 2 dimension makes.
*/

WITH versions AS (

  SELECT * FROM {{ ref('int_customer_versions') }}

)

SELECT
  {{ dbt_utils.generate_surrogate_key(['customer_id', 'valid_from']) }}
    AS customer_key,
  customer_id,
  version_number,
  valid_from,
  valid_to,
  is_current,

  -- Identity and contact. Classified; masked in the 40_secure layer.
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

  -- Compliance and commercial attributes: the reason this dimension is Type 2.
  kyc_status,
  risk_rating,
  customer_tier,
  marketing_opt_in,

  -- Derived, as at valid_from.
  DATEDIFF('year', date_of_birth, valid_from) AS age_years,
  CASE
    WHEN DATEDIFF('year', date_of_birth, valid_from) < 25 THEN '18-24'
    WHEN DATEDIFF('year', date_of_birth, valid_from) < 35 THEN '25-34'
    WHEN DATEDIFF('year', date_of_birth, valid_from) < 45 THEN '35-44'
    WHEN DATEDIFF('year', date_of_birth, valid_from) < 55 THEN '45-54'
    WHEN DATEDIFF('year', date_of_birth, valid_from) < 65 THEN '55-64'
    ELSE '65+'
  END AS age_band,
  DATEDIFF('day', CAST(created_at AS DATE), valid_from) AS tenure_days_at_version,

  -- Provenance: which extract this version was first seen in, and the hash that
  -- made it a new version. Both exist so that "why does this customer have four
  -- versions" is answerable without re-deriving the change detection by hand.
  observed_at_extract_date,
  attribute_hash,

  CAST(created_at AS DATE) AS signup_date,
  DATE_TRUNC('month', created_at) AS signup_month,
  kyc_status = 'verified' AS is_kyc_verified,

  created_at,
  updated_at,
FROM versions
