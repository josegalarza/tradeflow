# 0005 — `fct_positions_daily` keeps a trailing window, not full history

**Status:** accepted · **Date:** 2026-08-12

## Context

A periodic snapshot of holdings is the fact that makes portfolio analytics
possible: position quantity, market value and unrealised gain, per account, per
instrument, per day.

The naive grain is `accounts × instruments × days`. At the `medium` preset that is
33,750 accounts × 44 instruments × 730 days ≈ **1.1 billion rows**, of which
almost all are zero — nobody holds every instrument every day. At `large` it is
7 billion. This does not fit on a laptop, and the rows it would add carry no
information.

## Decision

Three things together:

1. **Only days with a non-zero holding exist as rows.** The running balance is
   computed at the dates it actually changes, each balance becomes the interval it
   stayed valid for, and only those intervals are expanded to daily rows. Cost
   becomes proportional to real position-days.
2. **A trailing window**, `positions_snapshot_days` (default 120), rather than
   full history.
3. **Incremental materialisation**, reprocessing a short lookback so late-arriving
   fills correct the days they belong to, then appending new days. History
   accumulates across runs rather than being rebuilt.

At the `small` preset this is 1.4M rows instead of ~59M for the naive spine.

## Why a window at all

Full daily history multiplies rows by the length of the dataset for a chart nobody
scrolls back through. The trailing window is a *hot* window: it is where the
questions are. The mechanism for extending it is already in place — raise the var,
or let the incremental build accumulate — so this is a default, not a ceiling.

`fct_account_daily` shares the same window, because its market-value component
comes from this model and simply does not exist outside it.

## The price join

A position exists every day it is held, including weekends and holidays. Equities
are only priced on trading days. An equi-join on date silently yields a NULL market
value for about 28% of rows — and a NULL that `SUM`s to an understated portfolio.

`ASOF LEFT JOIN` takes the most recent price at or before the snapshot date, which
is what "the position was worth this on Sunday" actually means. The share of rows
carrying a carried-forward price is exposed as `is_stale_price` and charted on the
dashboard's data quality page, because a number that is *supposed* to be 28% is
only reassuring if you can see it is still 28%.

## What is deliberately not modelled

`net_invested_reporting` is cumulative purchase cost less sale proceeds — net
capital deployed. It is **not** a weighted-average cost basis.

True average-cost accounting reduces the basis proportionally on every sale, which
is inherently sequential and would need a recursive CTE. Rather than implement it
badly, the column is named for what it is, and `unrealised_gain_reporting` is
honestly "gain against capital deployed". The realised half is recovered in
`fct_account_daily` by comparing capital deployed across all positions against
capital still sitting in open ones.

Naming a column `cost_basis` and computing something else would be the worse
outcome: the number would be used.

## Consequences

- Position history before the window is unavailable at daily grain. A monthly
  snapshot fact is the natural extension and is listed as deferred.
- The reconciliation test (`assert_positions_reconcile_to_executions`) samples
  rather than checking exhaustively: its correlated subquery is
  O(snapshots × fills), and at `large` the exhaustive form would outlast the build
  it checks. A systematic windowing error appears in the first few hundred rows,
  and that is the only kind of error this can have. The sample size is a var so CI
  can raise it.
- `positions_snapshot_days` couples two facts. Changing it changes the span of the
  equity curve as well as the position snapshot.
- Accumulating across runs is only valid while the landing zone is stable. The
  incremental build upserts by `(account, instrument, snapshot_date)` over a
  short lookback, which assumes the source is append-only. `ingestion.generate`
  is not: it wipes the landing zone and regenerates the whole history against a
  new end date, so re-running it a day later gives every fill a new date and
  leaves the snapshot rows outside the lookback describing a dataset that no
  longer exists. `assert_positions_reconcile_to_executions` catches this, which
  is the test doing its job. `make demo` therefore full-refreshes, and the plain
  incremental path (`make build`) is for repeated builds over one landing zone.
