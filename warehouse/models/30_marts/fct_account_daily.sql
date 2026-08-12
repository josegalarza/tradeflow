/*
  Periodic snapshot fact. One row per account per day the account was open,
  within the same trailing window as fct_positions_daily.

  Cash balance is a running total from the beginning of the account's life, not
  from the start of the window. Two sources feed it -- cash movements (deposits,
  withdrawals, fees, dividends) and the cash side of trades -- and the opening
  balance carried into the window is computed separately from the daily
  movements inside it. Restarting the running sum at the window boundary would
  produce an equity curve that is beautifully smooth and completely wrong.

  Equity is cash plus the market value of holdings, which is why this model
  shares fct_positions_daily's window: the market-value component simply does
  not exist outside it.
*/

WITH bounds AS (

  SELECT
    MIN(snapshot_date) AS window_start,
    MAX(snapshot_date) AS window_end,
  FROM {{ ref('fct_positions_daily') }}

),

accounts AS (

  SELECT * FROM {{ ref('dim_account') }}

),

fx AS (

  SELECT
    base_currency,
    rate_date,
    rate,
  FROM {{ ref('stg_fx_rates') }}
  WHERE quote_currency = '{{ var("reporting_currency") }}'

),

-- Cash movements, converted to the reporting currency on the day they settled.
movements AS (

  SELECT
    movements.account_id,
    movements.occurred_date AS activity_date,
    SUM(movements.amount * fx.rate) AS net_cash_movement_reporting,
    SUM(
      CASE WHEN movements.movement_type = 'deposit'
        THEN movements.amount * fx.rate ELSE 0 END
    ) AS deposits_reporting,
    SUM(
      CASE WHEN movements.movement_type = 'withdrawal'
        THEN -movements.amount * fx.rate ELSE 0 END
    ) AS withdrawals_reporting,
    SUM(
      CASE WHEN movements.movement_type = 'fee'
        THEN -movements.amount * fx.rate ELSE 0 END
    ) AS fees_reporting,
    SUM(
      CASE WHEN movements.movement_type IN ('dividend', 'interest')
        THEN movements.amount * fx.rate ELSE 0 END
    ) AS income_reporting,
  FROM {{ ref('stg_cash_movements') }} AS movements
  -- ASOF, consistent with every other FX join in the warehouse: convert at the
  -- most recent published rate rather than dropping the movement or silently
  -- multiplying it by NULL.
  ASOF LEFT JOIN fx
    ON movements.movement_currency = fx.base_currency
    AND fx.rate_date <= movements.occurred_date
  GROUP BY movements.account_id, movements.occurred_date

),

-- The cash side of trading: buys consume cash, sells release it.
trade_cash AS (

  SELECT
    account_id,
    executed_date AS activity_date,
    SUM(signed_cash_flow_reporting) AS trade_cash_flow_reporting,
    SUM(commission_reporting) AS commission_reporting,
    COUNT(*) AS fill_count,
    SUM(gross_notional_reporting) AS traded_notional_reporting,
    -- Capital deployed into holdings across *all* positions, including ones
    -- since closed. fct_positions_daily only knows about open positions, so
    -- without this the realised half of P&L would be invisible: a customer who
    -- bought at 100 and sold at 120 has their 20 sitting in cash with nothing
    -- in the warehouse explaining where it came from.
    SUM(
      CASE WHEN side = 'buy'
        THEN gross_notional_reporting
        ELSE -gross_notional_reporting
      END
    ) AS net_invested_change,
  FROM {{ ref('int_executions_priced') }}
  GROUP BY account_id, executed_date

),

daily_flows AS (

  SELECT
    COALESCE(movements.account_id, trade_cash.account_id) AS account_id,
    COALESCE(movements.activity_date, trade_cash.activity_date) AS activity_date,
    COALESCE(movements.net_cash_movement_reporting, 0)
      + COALESCE(trade_cash.trade_cash_flow_reporting, 0) AS net_cash_change,
    COALESCE(movements.deposits_reporting, 0) AS deposits_reporting,
    COALESCE(movements.withdrawals_reporting, 0) AS withdrawals_reporting,
    COALESCE(movements.fees_reporting, 0) AS fees_reporting,
    COALESCE(movements.income_reporting, 0) AS income_reporting,
    COALESCE(trade_cash.commission_reporting, 0) AS commission_reporting,
    COALESCE(trade_cash.fill_count, 0) AS fill_count,
    COALESCE(trade_cash.traded_notional_reporting, 0) AS traded_notional_reporting,
    COALESCE(trade_cash.net_invested_change, 0) AS net_invested_change,
  FROM movements
  FULL OUTER JOIN trade_cash
    ON movements.account_id = trade_cash.account_id
    AND movements.activity_date = trade_cash.activity_date

),

-- Everything that happened before the window opens, collapsed to one number
-- per account. This is the balance the window inherits.
opening_balances AS (

  SELECT
    daily_flows.account_id,
    SUM(daily_flows.net_cash_change) AS opening_cash_reporting,
    SUM(daily_flows.deposits_reporting) AS opening_deposits_reporting,
    SUM(daily_flows.withdrawals_reporting) AS opening_withdrawals_reporting,
    SUM(daily_flows.fees_reporting) AS opening_fees_reporting,
    SUM(daily_flows.income_reporting) AS opening_income_reporting,
    SUM(daily_flows.commission_reporting) AS opening_commission_reporting,
    SUM(daily_flows.net_invested_change) AS opening_net_invested_reporting,
  FROM daily_flows
  CROSS JOIN bounds
  WHERE daily_flows.activity_date < bounds.window_start
  GROUP BY daily_flows.account_id

),

spine AS (

  SELECT
    accounts.account_id,
    dim_date.date_day AS snapshot_date,
  FROM accounts
  CROSS JOIN bounds
  INNER JOIN {{ ref('dim_date') }} AS dim_date
    ON dim_date.date_day BETWEEN bounds.window_start AND bounds.window_end
  -- Only days the account actually existed. A closed account should stop
  -- appearing, not carry a flat line to the end of the window.
  WHERE dim_date.date_day >= accounts.opened_date
    AND (accounts.closed_date IS NULL OR dim_date.date_day <= accounts.closed_date)

),

accumulated AS (

  SELECT
    spine.account_id,
    spine.snapshot_date,
    COALESCE(opening_balances.opening_cash_reporting, 0)
      + COALESCE(
        SUM(daily_flows.net_cash_change) OVER account_to_date, 0
      ) AS cash_balance_reporting,
    COALESCE(opening_balances.opening_deposits_reporting, 0)
      + COALESCE(SUM(daily_flows.deposits_reporting) OVER account_to_date, 0)
      AS cumulative_deposits_reporting,
    COALESCE(opening_balances.opening_withdrawals_reporting, 0)
      + COALESCE(SUM(daily_flows.withdrawals_reporting) OVER account_to_date, 0)
      AS cumulative_withdrawals_reporting,
    -- Cumulative fees, income and commission from account inception. Present so
    -- that the accounting identity in
    -- tests/assert_account_equity_reconciles.sql can be evaluated on a single
    -- row: equity = net funded + income - fees - commission + unrealised gain.
    -- An identity that needs a self-join to check does not get checked.
    COALESCE(opening_balances.opening_fees_reporting, 0)
      + COALESCE(SUM(daily_flows.fees_reporting) OVER account_to_date, 0)
      AS cumulative_fees_reporting,
    COALESCE(opening_balances.opening_income_reporting, 0)
      + COALESCE(SUM(daily_flows.income_reporting) OVER account_to_date, 0)
      AS cumulative_income_reporting,
    COALESCE(opening_balances.opening_commission_reporting, 0)
      + COALESCE(SUM(daily_flows.commission_reporting) OVER account_to_date, 0)
      AS cumulative_commission_reporting,
    COALESCE(opening_balances.opening_net_invested_reporting, 0)
      + COALESCE(SUM(daily_flows.net_invested_change) OVER account_to_date, 0)
      AS cumulative_net_invested_all_reporting,
    COALESCE(daily_flows.net_cash_change, 0) AS net_cash_change,
    COALESCE(daily_flows.deposits_reporting, 0) AS deposits_reporting,
    COALESCE(daily_flows.withdrawals_reporting, 0) AS withdrawals_reporting,
    COALESCE(daily_flows.fees_reporting, 0) AS fees_reporting,
    COALESCE(daily_flows.income_reporting, 0) AS income_reporting,
    COALESCE(daily_flows.commission_reporting, 0) AS commission_reporting,
    COALESCE(daily_flows.fill_count, 0) AS fill_count,
    COALESCE(daily_flows.traded_notional_reporting, 0)
      AS traded_notional_reporting,
  FROM spine
  LEFT JOIN daily_flows
    ON spine.account_id = daily_flows.account_id
    AND spine.snapshot_date = daily_flows.activity_date
  LEFT JOIN opening_balances
    ON spine.account_id = opening_balances.account_id
  WINDOW account_to_date AS (
    PARTITION BY spine.account_id
    ORDER BY spine.snapshot_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
  )

),

holdings AS (

  SELECT
    account_id,
    snapshot_date,
    SUM(market_value_reporting) AS holdings_value_reporting,
    SUM(net_invested_reporting) AS net_invested_reporting,
    SUM(unrealised_gain_reporting) AS unrealised_gain_reporting,
    COUNT(*) AS open_position_count,
    COUNT(DISTINCT instrument_id) AS distinct_instruments_held,
  FROM {{ ref('fct_positions_daily') }}
  GROUP BY account_id, snapshot_date

)

SELECT
  accumulated.account_id,
  accumulated.snapshot_date,
  accounts.account_key,
  accounts.customer_id,
  accounts.account_type,
  accounts.base_currency,
  accounts.account_status,

  CAST(accumulated.cash_balance_reporting AS DECIMAL(18, 4))
    AS cash_balance_reporting,
  CAST(
    COALESCE(holdings.holdings_value_reporting, 0) AS DECIMAL(18, 4)
  ) AS holdings_value_reporting,
  CAST(
    accumulated.cash_balance_reporting
    + COALESCE(holdings.holdings_value_reporting, 0) AS DECIMAL(18, 4)
  ) AS account_equity_reporting,
  CAST(
    COALESCE(holdings.net_invested_reporting, 0) AS DECIMAL(18, 4)
  ) AS net_invested_reporting,
  CAST(
    COALESCE(holdings.unrealised_gain_reporting, 0) AS DECIMAL(18, 4)
  ) AS unrealised_gain_reporting,
  -- Realised gain is what capital deployed into *closed* positions came back as.
  -- Open positions still carry their capital in net_invested; anything the
  -- account has deployed beyond that has been sold, and the difference is the
  -- profit or loss it was sold for.
  CAST(
    COALESCE(holdings.net_invested_reporting, 0)
    - accumulated.cumulative_net_invested_all_reporting AS DECIMAL(18, 4)
  ) AS realised_gain_reporting,
  CAST(
    accumulated.cumulative_deposits_reporting
    - accumulated.cumulative_withdrawals_reporting AS DECIMAL(18, 4)
  ) AS net_funded_reporting,
  CAST(accumulated.cumulative_deposits_reporting AS DECIMAL(18, 4))
    AS cumulative_deposits_reporting,
  CAST(accumulated.cumulative_withdrawals_reporting AS DECIMAL(18, 4))
    AS cumulative_withdrawals_reporting,
  CAST(accumulated.cumulative_fees_reporting AS DECIMAL(18, 4))
    AS cumulative_fees_reporting,
  CAST(accumulated.cumulative_income_reporting AS DECIMAL(18, 4))
    AS cumulative_income_reporting,
  CAST(accumulated.cumulative_commission_reporting AS DECIMAL(18, 4))
    AS cumulative_commission_reporting,

  -- Daily movements
  CAST(accumulated.net_cash_change AS DECIMAL(18, 4)) AS net_cash_change,
  CAST(accumulated.deposits_reporting AS DECIMAL(18, 4)) AS deposits_reporting,
  CAST(accumulated.withdrawals_reporting AS DECIMAL(18, 4))
    AS withdrawals_reporting,
  CAST(accumulated.fees_reporting AS DECIMAL(18, 4)) AS fees_reporting,
  CAST(accumulated.income_reporting AS DECIMAL(18, 4)) AS income_reporting,
  CAST(accumulated.commission_reporting AS DECIMAL(18, 4))
    AS commission_reporting,
  accumulated.fill_count,
  CAST(accumulated.traded_notional_reporting AS DECIMAL(18, 4))
    AS traded_notional_reporting,

  COALESCE(holdings.open_position_count, 0) AS open_position_count,
  COALESCE(holdings.distinct_instruments_held, 0) AS distinct_instruments_held,
  accumulated.fill_count > 0 AS traded_today,
FROM accumulated
INNER JOIN accounts ON accumulated.account_id = accounts.account_id
LEFT JOIN holdings
  ON accumulated.account_id = holdings.account_id
  AND accumulated.snapshot_date = holdings.snapshot_date
