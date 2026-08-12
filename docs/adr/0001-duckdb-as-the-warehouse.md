# 0001 — DuckDB as the warehouse

**Status:** accepted · **Date:** 2026-08-12

## Context

This project exists to be read and run by strangers. That imposes a constraint
most warehouse choices never face: a reviewer must be able to clone the repo and
reach a populated warehouse without an account, a credential, or a bill.

It also has to be a *real* OLAP workload. Modelling a hundred million fills
against a columnar engine and modelling them against SQLite are different
exercises, and only one of them is analytics engineering.

## Decision

DuckDB, as a local file, as the only warehouse.

## Why

- **It is a genuine OLAP engine.** Columnar storage, vectorised execution, window
  functions, `QUALIFY`, `ASOF JOIN`, native Parquet. The `ASOF JOIN` in
  `fct_positions_daily` is not a curiosity — it is the correct answer to
  "what was this position worth on a Sunday", and most engines make you write a
  correlated subquery for it.
- **Zero setup means CI and a laptop run the same thing.** There is no "works on
  my machine" gap to explain, because there is no machine-specific
  configuration. A green CI run is evidence a local build works.
- **Reading Parquet in place.** The landing zone is read as external files rather
  than loaded, which is how a lakehouse actually behaves and keeps a full rebuild
  cheap.

## Alternatives considered

**Postgres.** Row-oriented. It would run the models, but it would misrepresent
the workload: the partition pruning, the columnar scans and the vectorised
aggregations that make the design choices in this repo *matter* would all be
absent. The models would look the same and mean something different.

**BigQuery or Snowflake.** The closest to what this project imitates, and
disqualified by the first constraint. Both need an account and a payment method,
neither can run in public CI, and a reviewer cannot verify a single claim in the
README without signing up. A portfolio piece nobody can run is a slide deck.

**ClickHouse or Trino locally.** Both are real OLAP engines and both need a
running service. That is a container, a health check and a port before anyone
sees a number, for no analytical gain over DuckDB at this scale.

## Consequences

- **No engine-enforced security.** DuckDB has no row-level security and no
  dynamic data masking, so the governance layer enforces policy by generating
  masked views per role rather than by asking the engine to do it. That boundary
  is stated explicitly in `governance/policy.yml` and in ADR 0003 — overclaiming
  it would be the worst outcome available.
- **Single-writer.** Fine for a warehouse built by one pipeline; it is the reason
  the dashboard opens the database `read_only=True`.
- **Relative paths are a trap.** DuckDB resolves a relative external path against
  whichever process opens the file, so the landing-zone root has to be absolute
  or the warehouse is readable from `warehouse/` and nowhere else. This cost an
  hour; the Makefile now exports `TRADEFLOW_LANDING_PATH` and the source
  definition reads it.
