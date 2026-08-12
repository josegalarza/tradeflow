# 0002 — dbt-core rather than Dataform

**Status:** accepted · **Date:** 2026-08-12

## Context

The transformation layer needs `ref()`-driven lineage, tests, documentation,
snapshots and a package ecosystem. Two tools were seriously considered: dbt-core
and Google Dataform. Both do the job; they fail different constraints.

## Decision

dbt-core, with the `dbt-duckdb` adapter.

## Why

- **It is warehouse-agnostic, and this project needs a local warehouse.** Dataform
  runs against BigQuery. Choosing it would have forced a cloud account back into
  the critical path and broken the "clone and run" promise that ADR 0001 is built
  around.
- **The test surface is the point.** Generic tests, singular tests, unit tests
  (fixed inputs and asserted outputs, no warehouse scan), source freshness and
  `store_failures` are all first-class. The unit tests covering SCD2 boundary
  construction would have to be hand-rolled anywhere else.
- **`manifest.json` is a governance API.** The entire classification framework —
  the CI gate, the generated role views, the data catalog — reads dbt's manifest.
  Getting a complete, structured description of every model and column for free is
  what makes the governance layer 300 lines instead of a parser.
- **It is the skill the market asks for.** Being honest about a portfolio's
  purpose: far more job descriptions name dbt than name Dataform.

## What Dataform would have been better at

Not nothing, and worth recording:

- **`sqlx` keeps config and SQL in one file.** dbt's split between a `.sql` model
  and a `.yml` schema entry is a real cost — the two drift, and this project hit
  exactly that: `dim_customer` documented two provenance columns it had stopped
  selecting, which only surfaced when the secure-view generator emitted SQL
  referencing a column that did not exist. The classification checker now reports
  documented-but-absent columns for that reason.
- **Assertions live next to the table they guard**, rather than in a separate
  block further down a YAML file.
- **No Python runtime.** Dataform is a JS/BigQuery-native tool with less to
  install.

## Consequences

- Model configuration is split across `.sql` and `.yml`, and the drift that
  invites is now caught by a check rather than by luck.
- `dbt-core` is pinned below 1.12 because `dagster-dbt` requires it. That is a
  real cost of the integration, recorded in ADR 0006.
- Two dbt packages are depended on (`dbt_utils`, `dbt_expectations`), which is two
  more things that can break on an upgrade — accepted for the test vocabulary
  they provide.
