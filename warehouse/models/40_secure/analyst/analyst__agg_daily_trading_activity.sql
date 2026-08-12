{#
  GENERATED FILE -- DO NOT EDIT.

  Written by governance/generate_secure_views.py from the classification tags in
  the dbt schema YAML and the role definitions in governance/policy.yml.

  To change what this role can see, edit the policy or the column's tags and run
  `make governance`. Editing this file directly will be reverted by the next
  generation, and CI checks that it matches.
#}

/*
  agg_daily_trading_activity as seen by the `analyst` role.

  Role clearance : internal
  Source model   : marts.agg_daily_trading_activity
  Columns        : 24 exposed, 0 masked, 0 withheld
*/

{{
  config(
    schema = 'secure_analyst',
    materialized = 'view',
    tags = ['secure', 'governance', 'role:analyst'],
  )
}}

SELECT
  date_day,
  channel,
  asset_class,
  order_count,
  filled_order_count,
  cancelled_order_count,
  rejected_order_count,
  trading_accounts,
  trading_customers,
  ordered_quantity,
  mean_seconds_to_first_fill,
  median_seconds_to_first_fill,
  fill_count,
  traded_notional_reporting,
  buy_notional_reporting,
  sell_notional_reporting,
  net_flow_reporting,
  commission_reporting,
  mean_slippage_vs_close,
  venues_used,
  instruments_traded,
  cancellation_rate,
  fill_rate,
  fills_per_filled_order,
FROM {{ ref('agg_daily_trading_activity') }}
