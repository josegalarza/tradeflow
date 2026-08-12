/*
  Type 2 history for the customer record, reconstructed from periodic extracts.

  The mechanism, in three steps:

  1. Hash the tracked attributes for every (customer, extract). Hashing rather
     than comparing 14 columns pairwise means adding a tracked attribute is a
     one-line change instead of a fourteen-clause boolean.
  2. Keep only the extracts where that hash differs from the customer's previous
     extract. Those are the version boundaries; everything else is an unchanged
     re-observation and would otherwise produce a new row per month per customer
     forever.
  3. Close each version with the day before the next one opens, and leave the
     last one open at 9999-12-31.

  Two decisions worth flagging:

  *`valid_from` for a customer's first version is their `created_at` date, not
  the date of the first extract that saw them.* The customer existed from the
  moment they signed up; dating their first version from an accident of extract
  scheduling would leave a gap that every `valid_from <= date < valid_to` join
  silently drops.

  *`valid_to` is inclusive, and closes the day before the next version opens.*
  Half-open intervals are the more common convention and are easier to reason
  about, but they make `BETWEEN` wrong, and `BETWEEN` is what an analyst
  writes. Choosing the convention that matches how the table will actually be
  queried avoids a class of off-by-one that produces plausible, slightly wrong
  numbers. The mutually_exclusive_ranges test enforces it.
*/

{{ config(materialized = 'table') }}

WITH extracts AS (

  SELECT * FROM {{ ref('stg_customer_extracts') }}

),

hashed AS (

  SELECT
    *,
    {{ dbt_utils.generate_surrogate_key([
      'first_name',
      'last_name',
      'email',
      'phone_number',
      'national_id',
      'street_address',
      'city',
      'postcode',
      'country_code',
      'kyc_status',
      'risk_rating',
      'customer_tier',
      'marketing_opt_in',
      'date_of_birth',
    ]) }} AS attribute_hash,
  FROM extracts

),

change_detected AS (

  SELECT
    *,
    LAG(attribute_hash) OVER (
      PARTITION BY customer_id ORDER BY extract_date
    ) AS previous_attribute_hash,
  FROM hashed

),

versions AS (

  SELECT * FROM change_detected
  WHERE previous_attribute_hash IS NULL
     OR previous_attribute_hash <> attribute_hash

),

bounded AS (

  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY customer_id ORDER BY extract_date
    ) AS version_number,
    LEAD(extract_date) OVER (
      PARTITION BY customer_id ORDER BY extract_date
    ) AS next_version_date,
  FROM versions

)

SELECT
  customer_id,
  version_number,
  CASE
    WHEN version_number = 1 THEN CAST(created_at AS DATE)
    ELSE extract_date
  END AS valid_from,
  COALESCE(
    next_version_date - INTERVAL 1 DAY,
    CAST('9999-12-31' AS DATE)
  ) AS valid_to,
  next_version_date IS NULL AS is_current,
  extract_date AS observed_at_extract_date,
  attribute_hash,

  first_name,
  last_name,
  full_name,
  email,
  phone_number,
  date_of_birth,
  national_id,
  street_address,
  city,
  postcode,
  country_code,
  kyc_status,
  risk_rating,
  customer_tier,
  marketing_opt_in,
  created_at,
  updated_at,
FROM bounded
