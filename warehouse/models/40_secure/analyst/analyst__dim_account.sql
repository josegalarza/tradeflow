{#
  GENERATED FILE -- DO NOT EDIT.

  Written by governance/generate_secure_views.py from the classification tags in
  the dbt schema YAML and the role definitions in governance/policy.yml.

  To change what this role can see, edit the policy or the column's tags and run
  `make governance`. Editing this file directly will be reverted by the next
  generation, and CI checks that it matches.
#}

/*
  dim_account as seen by the `analyst` role.

  Role clearance : internal
  Source model   : marts.dim_account
  Columns        : 20 exposed, 0 masked, 0 withheld
*/

{{
  config(
    schema = 'secure_analyst',
    materialized = 'view',
    tags = ['secure', 'governance', 'role:analyst'],
  )
}}

SELECT
  account_key,
  account_id,
  customer_id,
  account_type,
  base_currency,
  account_status,
  margin_limit,
  opened_at,
  opened_date,
  closed_at,
  closed_date,
  is_open,
  is_margin_enabled,
  opened_month,
  account_age_days,
  first_trade_date,
  latest_trade_date,
  lifetime_fill_count,
  has_ever_traded,
  days_to_first_trade,
FROM {{ ref('dim_account') }}
