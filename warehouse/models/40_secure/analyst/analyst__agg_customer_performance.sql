{#
  GENERATED FILE -- DO NOT EDIT.

  Written by governance/generate_secure_views.py from the classification tags in
  the dbt schema YAML and the role definitions in governance/policy.yml.

  To change what this role can see, edit the policy or the column's tags and run
  `make governance`. Editing this file directly will be reverted by the next
  generation, and CI checks that it matches.
#}

/*
  agg_customer_performance as seen by the `analyst` role.

  Role clearance : internal
  Source model   : marts.agg_customer_performance
  Columns        : 43 exposed, 3 masked, 0 withheld

  Masked:
    full_name                          redact
    email                              hash
    last_seen_at                       generalize
*/

{{
  config(
    schema = 'secure_analyst',
    materialized = 'view',
    tags = ['secure', 'governance', 'role:analyst'],
  )
}}

SELECT
  customer_key,
  customer_id,
  {{ mask_redact('full_name', 'VARCHAR') }} AS full_name,
  {{ mask_hash('email') }} AS email,
  country_code,
  customer_tier,
  risk_rating,
  kyc_status,
  age_band,
  marketing_opt_in,
  signup_date,
  signup_month,
  tenure_days,
  account_count,
  account_equity_reporting,
  cash_balance_reporting,
  holdings_value_reporting,
  net_funded_reporting,
  unrealised_gain_reporting,
  realised_gain_reporting,
  total_gain_reporting,
  open_position_count,
  lifetime_fill_count,
  lifetime_order_count,
  lifetime_cancelled_count,
  lifetime_traded_notional_reporting,
  lifetime_commission_reporting,
  mean_fill_notional_reporting,
  trading_days,
  distinct_instruments_traded,
  distinct_sectors_traded,
  first_trade_date,
  last_trade_date,
  largest_trade_symbol,
  primary_channel,
  lifetime_event_count,
  lifetime_session_count,
  app_active_days,
  {{ mask_generalize_timestamp('last_seen_at') }} AS last_seen_at,
  primary_device_family,
  return_on_funded,
  cancellation_rate,
  has_ever_traded,
FROM {{ ref('agg_customer_performance') }}
