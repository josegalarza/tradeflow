"""Dagster definitions for the tradeflow pipeline.

The whole warehouse appears in the Dagster UI as one asset graph: the landing
zone tables, then every dbt model individually, then the governance artefacts and
the static dashboard export. Every dbt test becomes a Dagster asset check on the
model it tests.

That per-model granularity is the point. Wrapping the warehouse in a single
"run dbt" op would give a lineage graph with one box in it -- no way to
materialise a subset, no per-model freshness, and a failure that says "dbt
failed" rather than "fct_positions_daily failed and these four assets downstream
are now stale".

Run it with::

    make dagster        # UI on http://localhost:3000

Deliberately not implemented: daily partitions with backfill. The generator
rewrites its whole window on every run, so partition-per-day would be a UI
affordance over an asset that does not actually support incremental
materialisation -- an orchestration story that looks better than it behaves. See
docs/adr/0006.
"""

# NOTE: deliberately no `from __future__ import annotations` here.
# Dagster inspects the runtime type of the `context` parameter to decide what to
# pass in, and postponed evaluation turns that annotation into a string it cannot
# resolve -- producing the memorably unhelpful "context must be annotated with
# AssetExecutionContext" on a parameter that already is.
import json
import os
import shutil
import sys
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    AssetKey,
    AssetSpec,
    DefaultScheduleStatus,
    Definitions,
    MaterializeResult,
    MetadataValue,
    RunFailureSensorContext,
    ScheduleDefinition,
    asset,
    define_asset_job,
    multi_asset,
    run_failure_sensor,
)
from dagster_dbt import DbtCliResource, DbtProject, dbt_assets

from orchestration.notifications import RunSummary, send

REPO_ROOT = Path(__file__).resolve().parent.parent
WAREHOUSE_DIR = REPO_ROOT / "warehouse"

# Absolute paths, exported for every subprocess. The staging models are views
# over the landing Parquet and DuckDB resolves relative paths against the
# reader's working directory, so Dagster launching dbt from a different cwd than
# the Makefile would silently produce "file not found" on every source.
os.environ.setdefault("TRADEFLOW_LANDING_PATH", str(REPO_ROOT / "data" / "landing"))
os.environ.setdefault("TRADEFLOW_DUCKDB", str(REPO_ROOT / "data" / "tradeflow.duckdb"))


def dbt_executable() -> str:
    """Locate dbt in the environment Dagster is itself running in.

    ``shutil.which`` alone is not enough: Dagster is frequently launched by an
    absolute path to the venv's python without the venv's bin/ on PATH, and dbt
    then appears to be missing. The interpreter's own directory is the reliable
    answer, and it holds inside a container as well as in a local venv.
    """
    alongside_python = Path(sys.executable).parent / "dbt"
    if alongside_python.exists():
        return str(alongside_python)
    found = shutil.which("dbt")
    if found:
        return found
    raise RuntimeError(
        "cannot find the dbt executable. Run `make install` so it lives in "
        f"{Path(sys.executable).parent}, or put dbt on PATH."
    )


dbt_project = DbtProject(
    project_dir=WAREHOUSE_DIR,
    profiles_dir=WAREHOUSE_DIR,
)
# In development this parses the project so the manifest exists before Dagster
# builds its asset graph; in production the manifest is expected to be built
# ahead of deployment.
dbt_project.prepare_if_dev()

#: The landing-zone tables, matching the dbt source names in
#: models/10_staging/_landing__sources.yml. dagster-dbt maps a dbt source
#: `landing.orders` to AssetKey(["landing", "orders"]), so declaring assets with
#: those keys is what joins the generator to the dbt graph instead of leaving two
#: disconnected islands in the UI.
LANDING_TABLES = [
    "instruments",
    "market_prices",
    "fx_rates",
    "customer_extracts",
    "accounts",
    "orders",
    "executions",
    "cash_movements",
    "app_events",
]

SCALE = os.environ.get("TRADEFLOW_SCALE", "small")
SEED = int(os.environ.get("TRADEFLOW_SEED", "42"))


@multi_asset(
    specs=[
        AssetSpec(
            key=AssetKey(["landing", table]),
            description=f"Synthetic {table} extract, written as Hive-partitioned Parquet.",
            kinds={"parquet", "python"},
            group_name="landing",
        )
        for table in LANDING_TABLES
    ],
    can_subset=False,
    description="Generate the full synthetic landing zone in one pass.",
)
def landing_zone(context: AssetExecutionContext):
    """Run the generator.

    ``can_subset=False`` because the entities are not independent: executions are
    derived from orders, which are derived from accounts. Allowing Dagster to
    materialise `landing/executions` alone would produce fills referencing orders
    that no longer exist -- exactly the orphan defect the warehouse screens for,
    manufactured by the orchestrator.
    """
    from datetime import date

    from ingestion.generate import Config, generate

    scale_days = {"tiny": 120, "small": 400, "medium": 730, "large": 1095}
    scale_customers = {"tiny": 250, "small": 2_500, "medium": 25_000, "large": 150_000}

    config = Config(
        customers=scale_customers[SCALE],
        days=scale_days[SCALE],
        seed=SEED,
        end_date=date.today(),
        out_dir=Path(os.environ["TRADEFLOW_LANDING_PATH"]),
        scale_name=SCALE,
    )
    context.log.info(
        f"generating scale={SCALE} seed={SEED} ({config.start_date} -> {config.end_date})"
    )
    stats = generate(config)

    for table in LANDING_TABLES:
        context.log.info(f"  {table}: {stats.rows.get(table, 0):,} rows")

    total = sum(stats.rows.values())
    return MaterializeResult(
        metadata={
            "scale": SCALE,
            "seed": SEED,
            "total_rows": MetadataValue.int(total),
            "elapsed_seconds": stats.elapsed_seconds,
            "row_counts": MetadataValue.json(stats.rows),
            "start_date": config.start_date.isoformat(),
            "end_date": config.end_date.isoformat(),
        }
    )


@dbt_assets(
    manifest=dbt_project.manifest_path,
    project=dbt_project,
)
def dbt_warehouse(context: AssetExecutionContext, dbt: DbtCliResource):
    """Every dbt model as its own asset, every dbt test as an asset check.

    `dbt build` rather than `run` then `test`: build interleaves them so a model's
    tests run as soon as it is ready and a failure stops its own subtree instead
    of the whole graph.
    """
    yield from dbt.cli(["build"], context=context).stream()


@asset(
    deps=[dbt_warehouse],
    group_name="governance",
    kinds={"python"},
    description=(
        "Classification coverage gate, layer boundary check, regenerated secure "
        "views and the data catalog."
    ),
)
def governance_artifacts(context: AssetExecutionContext) -> MaterializeResult:
    """Re-run the governance tools against the freshly built warehouse."""
    from governance import build_catalog, check_classification, check_layer_boundaries
    from governance.policy import Policy, load_models

    # The tools read the manifest, so it has to reflect the build that just ran.
    context.log.info("checking classification coverage")
    classification_status = check_classification.main([])
    layer_status = check_layer_boundaries.main([])
    build_catalog.main([])

    policy = Policy.load()
    models = load_models(policy=policy, include_generated=False)
    pii_columns = sum(1 for model in models for column in model.columns if column.is_pii)

    if classification_status != 0:
        raise RuntimeError(
            "classification gate failed -- a column requiring a classification "
            "does not have one. See the log above."
        )
    if layer_status != 0:
        raise RuntimeError("layer boundary check failed -- see the log above.")

    return MaterializeResult(
        metadata={
            "models": len(models),
            "pii_columns": pii_columns,
            "roles": MetadataValue.json(sorted(policy.roles)),
            "catalog": MetadataValue.path(str(REPO_ROOT / "docs" / "catalog.md")),
        }
    )


@asset(
    deps=[dbt_warehouse],
    group_name="reporting",
    kinds={"python", "plotly"},
    description="Static HTML dashboard export, publishable to GitHub Pages.",
)
def static_dashboard(context: AssetExecutionContext) -> MaterializeResult:
    from dashboard.export import export

    output = export()
    context.log.info(f"wrote {output}")
    return MaterializeResult(
        metadata={
            "path": MetadataValue.path(str(output)),
            "size_kb": round(output.stat().st_size / 1024, 1),
        }
    )


@asset(
    deps=[dbt_warehouse],
    group_name="reporting",
    kinds={"slack"},
    description=(
        "Post the build summary to Slack. Degrades to stdout when "
        "SLACK_WEBHOOK_URL is unset."
    ),
)
def build_notification(context: AssetExecutionContext) -> MaterializeResult:
    run_results = WAREHOUSE_DIR / "target" / "run_results.json"
    if not run_results.exists():
        context.log.warning("no run_results.json; nothing to summarise")
        return MaterializeResult(metadata={"delivered": False})

    summary = RunSummary.from_run_results(run_results)

    manifest = Path(os.environ["TRADEFLOW_LANDING_PATH"]) / "_manifest.json"
    if manifest.exists():
        summary.row_counts = json.loads(manifest.read_text()).get("row_counts", {})

    delivered = send(summary)
    return MaterializeResult(
        metadata={
            "delivered_to_slack": delivered,
            "models_built": summary.models_built,
            "tests_passed": summary.tests_passed,
            "tests_warned": summary.tests_warned,
            "tests_failed": summary.tests_failed,
        }
    )


# ---------------------------------------------------------------------------- #
# Jobs, schedules and sensors
# ---------------------------------------------------------------------------- #

daily_refresh = define_asset_job(
    name="daily_refresh",
    selection="*",
    description="Regenerate the landing zone, rebuild the warehouse, refresh governance and reporting.",
)

daily_schedule = ScheduleDefinition(
    job=daily_refresh,
    # 06:15 UTC: after an overnight batch would have landed, before anyone looks
    # at a dashboard.
    cron_schedule="15 6 * * *",
    default_status=DefaultScheduleStatus.STOPPED,
    description=(
        "Daily full refresh. Ships STOPPED so cloning the repo does not start a "
        "scheduler nobody asked for."
    ),
)


@run_failure_sensor(description="Post a Slack alert when any run fails.")
def slack_on_run_failure(context: RunFailureSensorContext):
    """Alert on failure.

    A failure sensor rather than a hook on each asset: the interesting event is
    "the run failed", once, not one message per failed asset. Twelve alerts for
    one incident is how alerting gets muted.
    """
    summary = RunSummary(
        target=os.environ.get("DBT_TARGET", "dev"),
        tests_failed=1,
        failures=[context.failure_event.message or context.dagster_run.job_name],
    )
    send(summary)
    context.log.info("failure notification dispatched")


defs = Definitions(
    assets=[
        landing_zone,
        dbt_warehouse,
        governance_artifacts,
        static_dashboard,
        build_notification,
    ],
    jobs=[daily_refresh],
    schedules=[daily_schedule],
    sensors=[slack_on_run_failure],
    resources={
        "dbt": DbtCliResource(
            project_dir=dbt_project,
            profiles_dir=str(WAREHOUSE_DIR),
            dbt_executable=dbt_executable(),
        ),
    },
)
