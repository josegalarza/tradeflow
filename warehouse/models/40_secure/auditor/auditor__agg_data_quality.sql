{#
  GENERATED FILE -- DO NOT EDIT.

  Written by governance/generate_secure_views.py from the classification tags in
  the dbt schema YAML and the role definitions in governance/policy.yml.

  To change what this role can see, edit the policy or the column's tags and run
  `make governance`. Editing this file directly will be reverted by the next
  generation, and CI checks that it matches.
#}

/*
  agg_data_quality as seen by the `auditor` role.

  Role clearance : restricted
  Source model   : marts.agg_data_quality
  Columns        : 9 exposed, 0 masked, 0 withheld
*/

{{
  config(
    schema = 'secure_auditor',
    materialized = 'view',
    tags = ['secure', 'governance', 'role:auditor'],
  )
}}

SELECT
  model_name,
  activity_date,
  reject_reason,
  total_rows,
  total_rejected_rows,
  rejected_rows,
  affected_quantity,
  reject_rate,
  overall_reject_rate,
FROM {{ ref('agg_data_quality') }}
