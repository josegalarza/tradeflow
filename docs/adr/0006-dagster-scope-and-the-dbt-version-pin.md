# 0006 — Dagster scope, and what the integration costs

**Status:** accepted · **Date:** 2026-08-12

## Context

The pipeline needs an orchestrator: something that knows the landing zone comes
before staging, that a failed model invalidates its descendants, and that can
show a stranger the shape of the system in one screen.

## Decision

Dagster, with `dagster-dbt` mapping every dbt model to its own asset and every dbt
test to an asset check. 78 assets and 244 asset checks, from `landing/orders`
through to `secure_analyst/analyst__dim_customer`.

## Why not Airflow

Airflow is named on more job descriptions, which is a genuine argument for a
portfolio piece. It lost on two counts:

- **Task-aware, not asset-aware.** Airflow orchestrates *operations*; the unit
  this warehouse cares about is a *table*. Dagster's asset graph is the model
  graph, so "which tables are stale" is a first-class question rather than
  something inferred from which tasks last succeeded.
- **Weight.** A scheduler, a webserver and a metadata database, in containers,
  before anyone sees a number. Dagster's `dagster dev` is one command against the
  same venv the rest of the project uses.

A parallel Airflow DAG demonstrating orchestrator-agnostic design is listed as
deferred, not dismissed.

## What the integration costs: the dbt version pin

`dagster-dbt` requires `dbt-core<1.12`. This project was developed on 1.12 and
pinned back to 1.11 to keep the integration.

That trade is worth stating plainly, because the alternative was available:
shelling out to `dbt build` from a single Dagster asset would have kept dbt 1.12
and cost the entire reason for using Dagster — no per-model lineage, no asset
checks, no selective materialisation, and a failure that says "dbt failed" rather
than naming the model. One dbt minor version is a cheaper price than a
one-box lineage graph. One environment, one dbt version. Revisit when
`dagster-dbt` supports 1.12.

## What is deliberately not implemented

**Daily partitions with backfill.** The plan called for them; they were dropped
after building the rest.

The generator rewrites its whole window on every run. Declaring daily partitions
over an asset that cannot materialise a single day would produce a UI affordance
that looks like incremental orchestration and is not one — a reviewer clicking a
partition would trigger a full regeneration. That is a worse outcome than not
claiming the feature.

Making it real means changing the generator to emit a single date on request,
which is a genuine piece of work and not a checkbox. `fct_positions_daily` is
already incremental with a lookback, so the warehouse half of the story exists;
the orchestration half is deferred honestly rather than faked.

**Also deferred:** a sensor reacting to new Parquet files (the schedule covers the
same ground for a batch pipeline), and asset freshness policies (they describe SLAs
this project does not have).

## Consequences

- `orchestration/definitions.py` deliberately omits `from __future__ import
  annotations`. Dagster inspects the runtime type of the `context` parameter, and
  postponed evaluation turns it into a string it cannot resolve — producing the
  memorably unhelpful "context must be annotated with `AssetExecutionContext`" on
  a parameter that already is.
- `landing_zone` is a `multi_asset` with `can_subset=False`. The landing tables are
  not independent — executions derive from orders, which derive from accounts — so
  allowing Dagster to materialise `landing/executions` alone would manufacture the
  exact orphan defect the warehouse screens for.
- The daily schedule ships **stopped**. Cloning a repo should not start a
  scheduler nobody asked for.
