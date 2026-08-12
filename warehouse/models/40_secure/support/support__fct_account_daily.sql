{#
  GENERATED FILE -- DO NOT EDIT.

  Written by governance/generate_secure_views.py from the classification tags in
  the dbt schema YAML and the role definitions in governance/policy.yml.

  To change what this role can see, edit the policy or the column's tags and run
  `make governance`. Editing this file directly will be reverted by the next
  generation, and CI checks that it matches.
#}

/*
  fct_account_daily as seen by the `support` role.

  Role clearance : confidential
  Source model   : marts.fct_account_daily
  Columns        : 30 exposed, 0 masked, 0 withheld
*/

{{
  config(
    schema = 'secure_support',
    materialized = 'view',
    tags = ['secure', 'governance', 'role:support'],
  )
}}

SELECT
  account_id,
  snapshot_date,
  account_key,
  customer_id,
  account_type,
  base_currency,
  account_status,
  cash_balance_reporting,
  holdings_value_reporting,
  account_equity_reporting,
  net_invested_reporting,
  unrealised_gain_reporting,
  realised_gain_reporting,
  net_funded_reporting,
  cumulative_deposits_reporting,
  cumulative_withdrawals_reporting,
  cumulative_fees_reporting,
  cumulative_income_reporting,
  cumulative_commission_reporting,
  net_cash_change,
  deposits_reporting,
  withdrawals_reporting,
  fees_reporting,
  income_reporting,
  commission_reporting,
  fill_count,
  traded_notional_reporting,
  open_position_count,
  distinct_instruments_held,
  traded_today,
FROM {{ ref('fct_account_daily') }}
