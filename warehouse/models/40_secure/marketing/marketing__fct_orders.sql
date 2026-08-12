{#
  GENERATED FILE -- DO NOT EDIT.

  Written by governance/generate_secure_views.py from the classification tags in
  the dbt schema YAML and the role definitions in governance/policy.yml.

  To change what this role can see, edit the policy or the column's tags and run
  `make governance`. Editing this file directly will be reverted by the next
  generation, and CI checks that it matches.
#}

/*
  fct_orders as seen by the `marketing` role.

  Role clearance : internal
  Source model   : marts.fct_orders
  Columns        : 41 exposed, 0 masked, 0 withheld
*/

{{
  config(
    schema = 'secure_marketing',
    materialized = 'view',
    tags = ['secure', 'governance', 'role:marketing'],
  )
}}

SELECT
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
  time_in_force,
  order_status,
  channel,
  account_type,
  asset_class,
  sector,
  placed_at,
  first_filled_at,
  last_filled_at,
  resolved_at,
  order_quantity,
  filled_quantity,
  unfilled_quantity,
  fill_count,
  venue_count,
  filled_notional_reporting,
  commission_reporting,
  average_fill_price,
  primary_venue,
  limit_price,
  seconds_to_first_fill,
  seconds_to_last_fill,
  seconds_to_resolution,
  is_filled_any,
  is_fully_filled,
  is_cancelled,
  is_rejected,
  placed_hour,
  fill_rate,
  price_improvement_vs_limit,
FROM {{ ref('fct_orders') }}
