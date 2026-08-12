/*
  The gate.

  Individual malformed rows are operational noise -- a retry landed twice, a CRM
  export dropped a field. The quarantine layer absorbs them and agg_data_quality
  counts them. Failing a build over one bad row in fifty thousand would train
  everyone to ignore the build.

  A sustained *rate* of malformed rows is different: it means an upstream system
  has changed shape, and every number downstream is now suspect. That is what
  this test catches, and why it sits at error severity while the staging
  detectors only warn.

  Threshold is per model per day rather than overall: a single badly-broken day
  matters even when the 90-day average looks fine, and an overall average is
  exactly the statistic that hides an incident.
*/

{{ config(severity = 'error') }}

SELECT
  model_name,
  activity_date,
  total_rows,
  total_rejected_rows,
  overall_reject_rate,
  {{ var('max_reject_rate') }} AS threshold,
FROM {{ ref('agg_data_quality') }}
WHERE overall_reject_rate > {{ var('max_reject_rate') }}
  -- Ignore days too small for a rate to mean anything: one bad row out of three
  -- is a 33% reject rate and no evidence of anything.
  AND total_rows >= {{ var('min_rows_for_reject_rate') }}
GROUP BY ALL
