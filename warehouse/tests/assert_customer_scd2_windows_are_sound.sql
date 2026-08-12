/*
  The Type 2 contract, checked against this warehouse's actual convention.

  Three ways an SCD2 dimension goes wrong, each with a different downstream
  symptom:

  * *Overlapping windows.* Two versions valid on the same date means every fact
    joining through that customer on that date is silently duplicated. Revenue
    goes up, nobody knows why.
  * *Gaps between windows.* A date with no valid version means facts on that date
    resolve to NULL and vanish from any inner-joined report. Revenue goes down,
    nobody knows why.
  * *Multiple current versions.* `WHERE is_current` -- the most common query
    against this table -- starts returning duplicate customers.

  `valid_to` is inclusive here, so contiguity means the next version opens
  exactly one day after the previous one closes. dbt_utils.mutually_exclusive_
  ranges assumes half-open bounds and would flag every correct boundary as a
  gap, which is why this is written out rather than configured.
*/

WITH ordered AS (

  SELECT
    customer_id,
    version_number,
    valid_from,
    valid_to,
    is_current,
    LEAD(valid_from) OVER (
      PARTITION BY customer_id ORDER BY valid_from
    ) AS next_valid_from,
    COUNT_IF(is_current) OVER (PARTITION BY customer_id) AS current_versions,
  FROM {{ ref('dim_customer') }}

),

violations AS (

  SELECT
    customer_id,
    version_number,
    valid_from,
    valid_to,
    next_valid_from,
    'overlapping_versions' AS violation,
  FROM ordered
  WHERE next_valid_from IS NOT NULL
    AND next_valid_from <= valid_to

  UNION ALL

  SELECT
    customer_id,
    version_number,
    valid_from,
    valid_to,
    next_valid_from,
    'gap_between_versions' AS violation,
  FROM ordered
  WHERE next_valid_from IS NOT NULL
    AND next_valid_from <> valid_to + INTERVAL 1 DAY

  UNION ALL

  SELECT
    customer_id,
    version_number,
    valid_from,
    valid_to,
    next_valid_from,
    'inverted_window' AS violation,
  FROM ordered
  WHERE valid_to < valid_from

  UNION ALL

  SELECT
    customer_id,
    version_number,
    valid_from,
    valid_to,
    next_valid_from,
    'expected_exactly_one_current_version' AS violation,
  FROM ordered
  WHERE current_versions <> 1

)

SELECT * FROM violations
