/*
  The position snapshot must equal the running sum of the fills that produced it.

  `fct_positions_daily` gets its quantities from a window function over
  `int_position_movements`, then expands date intervals into daily rows. Both
  steps are places where an off-by-one produces a number that is wrong by one
  day's trading -- invisible in a chart, and material to a customer.

  This test rebuilds each snapshot independently from `fct_executions`: the
  position on day D must be the sum of every signed fill up to and including D.
  Two different routes to the same number, which is the only kind of check worth
  writing for derived state.

  Sampled rather than exhaustive. The correlated subquery is O(rows x fills) and
  at `--scale large` the exhaustive form would take longer than the build it is
  checking; a uniform sample of a few thousand snapshots catches a systematic
  error immediately, and a systematic error is the only kind this can have. The
  sample size is a var so CI can raise it.
*/

WITH sampled_snapshots AS (

  SELECT
    account_id,
    instrument_id,
    snapshot_date,
    position_quantity,
  FROM {{ ref('fct_positions_daily') }}
  -- noqa: PRS -- `USING SAMPLE` is valid DuckDB; SQLFluff's duckdb grammar does
  -- not cover it yet, so the parse error is the linter's gap, not a syntax error.
  USING SAMPLE {{ var('reconciliation_sample_rows') }} ROWS  -- noqa: PRS

),

recomputed AS (

  SELECT
    sampled_snapshots.*,
    (
      SELECT COALESCE(SUM(executions.signed_quantity), 0)
      FROM {{ ref('fct_executions') }} AS executions
      WHERE executions.account_id = sampled_snapshots.account_id
        AND executions.instrument_id = sampled_snapshots.instrument_id
        AND executions.date_day <= sampled_snapshots.snapshot_date
    ) AS quantity_from_fills,
  FROM sampled_snapshots

)

SELECT
  account_id,
  instrument_id,
  snapshot_date,
  position_quantity,
  quantity_from_fills,
  position_quantity - quantity_from_fills AS difference,
FROM recomputed
-- Tolerance covers DECIMAL(28,8) dust from fractional crypto fills.
WHERE ABS(position_quantity - quantity_from_fills) > 0.00000001
