{#
  GENERATED FILE -- DO NOT EDIT.

  Written by governance/generate_secure_views.py from the classification tags in
  the dbt schema YAML and the role definitions in governance/policy.yml.

  To change what this role can see, edit the policy or the column's tags and run
  `make governance`. Editing this file directly will be reverted by the next
  generation, and CI checks that it matches.
#}

/*
  fct_positions_daily as seen by the `auditor` role.

  Role clearance : restricted
  Source model   : marts.fct_positions_daily
  Columns        : 19 exposed, 0 masked, 0 withheld
*/

{{
  config(
    schema = 'secure_auditor',
    materialized = 'view',
    tags = ['secure', 'governance', 'role:auditor'],
  )
}}

SELECT
  account_id,
  instrument_id,
  snapshot_date,
  account_key,
  instrument_key,
  customer_id,
  symbol,
  asset_class,
  sector,
  position_quantity,
  mark_price,
  mark_price_date,
  is_stale_price,
  fx_rate_to_reporting,
  market_value_reporting,
  net_invested_reporting,
  unrealised_gain_reporting,
  cumulative_commission_reporting,
  days_since_last_trade,
FROM {{ ref('fct_positions_daily') }}
