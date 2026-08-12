{#
  GENERATED FILE -- DO NOT EDIT.

  Written by governance/generate_secure_views.py from the classification tags in
  the dbt schema YAML and the role definitions in governance/policy.yml.

  To change what this role can see, edit the policy or the column's tags and run
  `make governance`. Editing this file directly will be reverted by the next
  generation, and CI checks that it matches.
#}

/*
  agg_customer_performance as seen by the `support` role.

  Role clearance : confidential
  Source model   : marts.agg_customer_performance
  Columns        : 43 exposed, 1 masked, 0 withheld

  Masked:
    email                              partial
*/

{{
  config(
    schema = 'secure_support',
    materialized = 'view',
    tags = ['secure', 'governance', 'role:support'],
  )
}}

SELECT
  customer_key,
  customer_id,
  full_name,
  {{ mask_partial_email('email') }} AS email,
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
  last_seen_at,
  primary_device_family,
  return_on_funded,
  cancellation_rate,
  has_ever_traded,
FROM {{ ref('agg_customer_performance') }}
