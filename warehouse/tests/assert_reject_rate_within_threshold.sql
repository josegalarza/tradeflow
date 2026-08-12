/*
  The gate.

  Individual malformed rows are operational noise -- a retry landed twice, a CRM
  export dropped a field. The quarantine absorbs them and agg_data_quality counts
  them. Failing a build over one bad row in fifty thousand would train everyone to
  ignore the build.

  A sustained *rate* of malformed rows is different: it means an upstream system
  has changed shape, and every number downstream is now suspect. That is what this
  test catches, and why it sits at error severity while the staging detectors only
  warn.

  It checks two scopes, and it needs both:

  * **single_day** -- one badly-broken day matters even when the 90-day average
    looks fine. An overall average is exactly the statistic that hides an incident.
  * **all_time** -- the overall rate across the window. This is the scope that
    makes the gate work at any data volume, and it was added after CI proved the
    point: at `--scale tiny` no single day carries enough rows to compute a
    meaningful rate, every day was excluded by the minimum-rows floor, and the
    gate passed a build of deliberately corrupted data. A gate that only fires on
    large datasets is not a gate.

  Both scopes ignore samples too small for a rate to mean anything: one bad row out
  of three is a 33% reject rate and evidence of nothing.
*/

{{ config(severity = 'error') }}

WITH per_day AS (

  -- agg_data_quality carries one row per model, date and reject reason, with the
  -- day's totals repeated on each. Collapse back to one row per model per day.
  SELECT
    model_name,
    activity_date,
    ANY_VALUE(total_rows) AS total_rows,
    ANY_VALUE(total_rejected_rows) AS rejected_rows,
    ANY_VALUE(overall_reject_rate) AS reject_rate,
  FROM {{ ref('agg_data_quality') }}
  GROUP BY model_name, activity_date

),

daily_breaches AS (

  SELECT
    'single_day' AS scope,
    model_name,
    CAST(activity_date AS VARCHAR) AS measured_over,
    total_rows,
    rejected_rows,
    reject_rate,
  FROM per_day
  WHERE reject_rate > {{ var('max_reject_rate') }}
    AND total_rows >= {{ var('min_rows_for_reject_rate') }}

),

all_time AS (

  SELECT
    model_name,
    SUM(total_rows) AS total_rows,
    SUM(rejected_rows) AS rejected_rows,
    SUM(rejected_rows) / NULLIF(SUM(total_rows), 0) AS reject_rate,
  FROM per_day
  GROUP BY model_name

),

all_time_breaches AS (

  SELECT
    'all_time' AS scope,
    model_name,
    'every date in range' AS measured_over,
    total_rows,
    rejected_rows,
    reject_rate,
  FROM all_time
  WHERE reject_rate > {{ var('max_reject_rate') }}
    AND total_rows >= {{ var('min_rows_for_reject_rate') }}

)

SELECT
  *,
  {{ var('max_reject_rate') }} AS threshold,
FROM daily_breaches
UNION ALL
SELECT
  *,
  {{ var('max_reject_rate') }} AS threshold,
FROM all_time_breaches
