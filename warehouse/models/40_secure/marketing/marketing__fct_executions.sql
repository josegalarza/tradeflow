{#
  GENERATED FILE -- DO NOT EDIT.

  Written by governance/generate_secure_views.py from the classification tags in
  the dbt schema YAML and the role definitions in governance/policy.yml.

  To change what this role can see, edit the policy or the column's tags and run
  `make governance`. Editing this file directly will be reverted by the next
  generation, and CI checks that it matches.
#}

/*
  fct_executions as seen by the `marketing` role.

  Role clearance : internal
  Source model   : marts.fct_executions
  Columns        : 33 exposed, 0 masked, 0 withheld
*/

{{
  config(
    schema = 'secure_marketing',
    materialized = 'view',
    tags = ['secure', 'governance', 'role:marketing'],
  )
}}

SELECT
  execution_id,
  order_id,
  account_key,
  customer_key,
  instrument_key,
  date_day,
  account_id,
  customer_id,
  instrument_id,
  symbol,
  side,
  order_type,
  channel,
  account_type,
  venue,
  asset_class,
  sector,
  execution_currency,
  execution_quantity,
  signed_quantity,
  execution_price,
  gross_notional,
  gross_notional_reporting,
  commission,
  commission_reporting,
  signed_cash_flow_reporting,
  fx_rate_to_reporting,
  slippage_vs_close,
  commission_rate,
  order_placed_at,
  executed_at,
  seconds_from_order_to_fill,
  execution_hour,
FROM {{ ref('fct_executions') }}
