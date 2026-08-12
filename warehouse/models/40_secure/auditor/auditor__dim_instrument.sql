{#
  GENERATED FILE -- DO NOT EDIT.

  Written by governance/generate_secure_views.py from the classification tags in
  the dbt schema YAML and the role definitions in governance/policy.yml.

  To change what this role can see, edit the policy or the column's tags and run
  `make governance`. Editing this file directly will be reverted by the next
  generation, and CI checks that it matches.
#}

/*
  dim_instrument as seen by the `auditor` role.

  Role clearance : restricted
  Source model   : marts.dim_instrument
  Columns        : 21 exposed, 0 masked, 0 withheld
*/

{{
  config(
    schema = 'secure_auditor',
    materialized = 'view',
    tags = ['secure', 'governance', 'role:auditor'],
  )
}}

SELECT
  instrument_key,
  instrument_id,
  symbol,
  instrument_name,
  asset_class,
  exchange,
  sector,
  listing_currency,
  dividend_yield,
  is_active,
  listed_date,
  trades_every_day,
  is_reporting_currency,
  pays_dividend,
  latest_close_price,
  latest_price_date,
  latest_daily_return,
  first_price_date,
  all_time_low_price,
  all_time_high_price,
  average_daily_volume,
FROM {{ ref('dim_instrument') }}
