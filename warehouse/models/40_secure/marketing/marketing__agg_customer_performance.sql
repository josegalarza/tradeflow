{#
  GENERATED FILE -- DO NOT EDIT.

  Written by governance/generate_secure_views.py from the classification tags in
  the dbt schema YAML and the role definitions in governance/policy.yml.

  To change what this role can see, edit the policy or the column's tags and run
  `make governance`. Editing this file directly will be reverted by the next
  generation, and CI checks that it matches.
#}

/*
  agg_customer_performance as seen by the `marketing` role.

  Role clearance : internal
  Source model   : marts.agg_customer_performance
  Columns        : 27 exposed, 0 masked, 16 withheld

  Withheld entirely (above clearance, and this role omits
  rather than masks -- a masked column still advertises that
  the data exists):
    full_name (confidential)
    email (restricted)
    risk_rating (confidential)
    kyc_status (confidential)
    account_equity_reporting (confidential)
    cash_balance_reporting (confidential)
    holdings_value_reporting (confidential)
    net_funded_reporting (confidential)
    unrealised_gain_reporting (confidential)
    realised_gain_reporting (confidential)
    total_gain_reporting (confidential)
    lifetime_traded_notional_reporting (confidential)
    lifetime_commission_reporting (confidential)
    mean_fill_notional_reporting (confidential)
    last_seen_at (confidential)
    return_on_funded (confidential)
*/

{{
  config(
    schema = 'secure_marketing',
    materialized = 'view',
    tags = ['secure', 'governance', 'role:marketing'],
  )
}}

SELECT
  customer_key,
  customer_id,
  country_code,
  customer_tier,
  age_band,
  marketing_opt_in,
  signup_date,
  signup_month,
  tenure_days,
  account_count,
  open_position_count,
  lifetime_fill_count,
  lifetime_order_count,
  lifetime_cancelled_count,
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
  primary_device_family,
  cancellation_rate,
  has_ever_traded,
FROM {{ ref('agg_customer_performance') }}
