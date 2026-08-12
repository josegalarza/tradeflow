/*
  Calendar dimension covering the full range of observed market data.

  The trading-day flag is derived from the data rather than from a hardcoded
  holiday list: a date is a trading day if any equity or ETF has a price for it.
  A hardcoded list is wrong the moment an exchange announces an unscheduled
  closure, and it has to be maintained forever; the price feed already knows.

  The primary key is `date_day`, a real DATE. `date_key` is provided as an
  integer for anyone who expects the classic Kimball smart key, but the facts
  join on the date. In a columnar engine a DATE is four bytes, sorts correctly
  and prunes partitions; the integer surrogate exists to paper over
  cross-database date handling, which is not a problem this warehouse has.

  Fiscal year follows the Australian convention (July to June) because the
  broker's largest non-US market is Australia.
*/

WITH observed_ranges AS (

  -- The calendar must span every fact, not just the price feed. Deriving the
  -- range from prices alone left a real gap: a fill placed minutes before the
  -- close can be timestamped after midnight, landing a day past the last
  -- priced session, and every date join then silently dropped it. Widening the
  -- spine to the union of all observed activity is the fix; the
  -- `date_day -> dim_date` relationships tests on the facts are what stop it
  -- coming back.
  SELECT MIN(price_date) AS min_date, MAX(price_date) AS max_date
  FROM {{ ref('stg_market_prices') }}
  UNION ALL
  SELECT MIN(placed_date), MAX(placed_date) FROM {{ ref('stg_orders') }}
  UNION ALL
  SELECT MIN(executed_date), MAX(executed_date) FROM {{ ref('stg_executions') }}
  UNION ALL
  SELECT MIN(occurred_date), MAX(occurred_date)
  FROM {{ ref('stg_cash_movements') }}
  UNION ALL
  SELECT MIN(event_date), MAX(event_date) FROM {{ ref('stg_app_events') }}
  UNION ALL
  SELECT MIN(opened_date), MAX(opened_date) FROM {{ ref('stg_accounts') }}

),

bounds AS (

  SELECT
    MIN(min_date) AS range_start,
    MAX(max_date) AS range_end,
  FROM observed_ranges

),

spine AS (

  SELECT
    CAST(UNNEST(
      GENERATE_SERIES(range_start, range_end, INTERVAL 1 DAY)
    ) AS DATE) AS date_day,
  FROM bounds

),

trading_days AS (

  SELECT DISTINCT price_date
  FROM {{ ref('stg_market_prices') }}
  -- Crypto trades every day, so including it would mark every date a trading
  -- day and make the flag useless.
  WHERE instrument_id IN (
    SELECT instrument_id
    FROM {{ ref('stg_instruments') }}
    WHERE asset_class <> 'crypto'
  )

)

SELECT
  spine.date_day,
  CAST(STRFTIME(spine.date_day, '%Y%m%d') AS INTEGER) AS date_key,

  -- Day
  DAYOFWEEK(spine.date_day) AS day_of_week,
  DAYNAME(spine.date_day) AS day_name,
  DAYOFYEAR(spine.date_day) AS day_of_year,
  DAYOFWEEK(spine.date_day) BETWEEN 1 AND 5 AS is_weekday,
  trading_days.price_date IS NOT NULL AS is_trading_day,

  -- Week
  DATE_TRUNC('week', spine.date_day) AS week_start_date,
  WEEKOFYEAR(spine.date_day) AS week_of_year,

  -- Month
  DATE_TRUNC('month', spine.date_day) AS month_start_date,
  MONTH(spine.date_day) AS month_number,
  MONTHNAME(spine.date_day) AS month_name,
  STRFTIME(spine.date_day, '%Y-%m') AS year_month,
  spine.date_day = LAST_DAY(spine.date_day) AS is_month_end,
  spine.date_day = DATE_TRUNC('month', spine.date_day) AS is_month_start,

  -- Quarter and year
  QUARTER(spine.date_day) AS quarter_number,
  'Q' || QUARTER(spine.date_day) AS quarter_name,
  YEAR(spine.date_day) AS calendar_year,
  YEAR(spine.date_day)
    + CASE WHEN MONTH(spine.date_day) >= 7 THEN 1 ELSE 0 END AS fiscal_year,

  -- Relative position, for "last 30 days"-style filters that should not need a
  -- date function in every consuming query.
  DATEDIFF('day', spine.date_day, CURRENT_DATE) AS days_ago,
FROM spine
LEFT JOIN trading_days ON spine.date_day = trading_days.price_date
