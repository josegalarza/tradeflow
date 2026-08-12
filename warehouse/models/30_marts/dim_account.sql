/*
  Account dimension, Type 1.

  Type 1 because nothing on an account changes in a way anyone needs history
  for: the type, currency and margin limit are set at opening, and closure is
  already modelled as a timestamp rather than a mutating status. Making this
  Type 2 as well would double the join complexity of every fact for no
  analytical gain -- Type 2 is a cost you pay when history matters, not a badge.

  Carries `customer_id` rather than `customer_key`: the account's owner does not
  change, so pinning it to one version of the customer would be arbitrary. Facts
  resolve the customer version from their own event date.
*/

WITH accounts AS (

  SELECT * FROM {{ ref('stg_accounts') }}

),

first_activity AS (

  SELECT
    account_id,
    MIN(executed_date) AS first_trade_date,
    MAX(executed_date) AS latest_trade_date,
    COUNT(*) AS lifetime_fill_count,
  FROM {{ ref('int_executions_priced') }}
  GROUP BY account_id

)

SELECT
  {{ dbt_utils.generate_surrogate_key(['accounts.account_id']) }} AS account_key,
  accounts.account_id,
  accounts.customer_id,
  accounts.account_type,
  accounts.base_currency,
  accounts.account_status,
  accounts.margin_limit,
  accounts.opened_at,
  accounts.opened_date,
  accounts.closed_at,
  accounts.closed_date,

  -- Derived lifecycle attributes, so consumers do not each re-derive them.
  accounts.account_status = 'open' AS is_open,
  accounts.account_type = 'margin' AS is_margin_enabled,
  DATE_TRUNC('month', accounts.opened_at) AS opened_month,
  DATEDIFF(
    'day',
    accounts.opened_date,
    COALESCE(accounts.closed_date, CURRENT_DATE)
  ) AS account_age_days,
  first_activity.first_trade_date,
  first_activity.latest_trade_date,
  COALESCE(first_activity.lifetime_fill_count, 0) AS lifetime_fill_count,
  first_activity.account_id IS NOT NULL AS has_ever_traded,
  DATEDIFF(
    'day', accounts.opened_date, first_activity.first_trade_date
  ) AS days_to_first_trade,
FROM accounts
LEFT JOIN first_activity ON accounts.account_id = first_activity.account_id
