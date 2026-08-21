# tradeflow -- local-first analytics engineering platform
#
# `make demo` is the entry point: from a clean clone to a populated warehouse and
# a running dashboard, with no cloud account and no credentials.
#
# Every target is what CI runs, so a green CI run is evidence that a local build
# works rather than evidence that CI has its own special path.

.DEFAULT_GOAL := help
SHELL := /bin/bash

VENV        := .venv
PYTHON      := $(VENV)/bin/python
PIP         := $(VENV)/bin/pip
DBT         := $(VENV)/bin/dbt
WAREHOUSE   := warehouse

# Interpreter used to CREATE the venv. This needs to be found rather than
# assumed: the project requires Python >= 3.11 (numpy 2.3 and the dbt pins), and
# a machine's bare `python3` is frequently older -- a pyenv global, a distro
# default. Using it produced a fresh-clone failure whose only symptom was
# "No matching distribution found for numpy~=2.3.0", which says nothing about
# the actual cause.
#
# Picks the newest supported interpreter available. Override explicitly with:
#   make install PYTHON_BIN=/opt/homebrew/bin/python3.12
PYTHON_BIN ?= $(shell for p in python3.13 python3.12 python3.11 python3; do \
	  if command -v $$p >/dev/null 2>&1 && \
	     $$p -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)' \
	     >/dev/null 2>&1; then echo $$p; break; fi; \
	done)

# Absolute path to the landing zone. The staging models are views over these
# files and DuckDB resolves relative paths against whichever process opens the
# database -- so a relative path here makes the warehouse readable from
# warehouse/ and nowhere else, breaking the dashboard and Dagster.
export TRADEFLOW_LANDING_PATH := $(CURDIR)/data/landing
export TRADEFLOW_DUCKDB       := $(CURDIR)/data/tradeflow.duckdb
export DBT_PROFILES_DIR       := $(CURDIR)/$(WAREHOUSE)

# Row-count preset for the generator: tiny | small | medium | large.
SCALE ?= small
SEED  ?= 42
# dbt selector, e.g. `make build SELECT=fct_executions+`
SELECT ?=
DBT_SELECT := $(if $(SELECT),--select $(SELECT),)

.PHONY: help
help: ## Show this help
	@echo "tradeflow -- make targets"
	@echo
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "  Variables: SCALE=$(SCALE) (tiny|small|medium|large)  SEED=$(SEED)  SELECT="
	@echo

# ---------------------------------------------------------------------------- #
# Setup
# ---------------------------------------------------------------------------- #

define require_python
	@if [ -z "$(PYTHON_BIN)" ]; then \
	  echo "error: no Python >= 3.11 found on PATH."; \
	  echo "  This project needs 3.11 or newer (numpy 2.3, dbt 1.11)."; \
	  echo "  Install one, or point at it directly:"; \
	  echo "    make install PYTHON_BIN=/path/to/python3.12"; \
	  exit 1; \
	fi
	@echo "using $(PYTHON_BIN) ($$($(PYTHON_BIN) --version 2>&1))"
endef

.PHONY: install
install: ## Create the venv and install everything
	$(call require_python)
	$(PYTHON_BIN) -m venv $(VENV)
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -r requirements/dev.txt
	$(PIP) install --quiet -r requirements/orchestration.txt
	$(PIP) install --quiet -r requirements/dashboard.txt
	cd $(WAREHOUSE) && ../$(DBT) deps
	@echo "installed. next: make demo"

.PHONY: install-core
install-core: ## Install only what `make build` needs (used by CI)
	$(call require_python)
	$(PYTHON_BIN) -m venv $(VENV)
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -r requirements/dev.txt
	cd $(WAREHOUSE) && ../$(DBT) deps

# ---------------------------------------------------------------------------- #
# The demo
# ---------------------------------------------------------------------------- #

# `rebuild`, not `build`: `generate` wipes the landing zone and regenerates the
# whole history against a new end date (UTC yesterday), so every fill gets a new
# date on every run. `fct_positions_daily` is incremental and upserts by
# (account, instrument, snapshot_date) over a short lookback -- a contract that
# assumes the source is append-only. Re-running `make demo` a day or more after
# the last build therefore left months of snapshot rows computed from the
# *previous* dataset, and `assert_positions_reconcile_to_executions` correctly
# failed on them. Incremental state is only valid across runs that share a
# landing zone, which `generate` never does. `make build` keeps the plain
# incremental path for exactly that case.
.PHONY: demo
demo: generate rebuild governance ## Clean clone -> populated warehouse (start here)
	@echo
	@echo "warehouse built at $(TRADEFLOW_DUCKDB)"
	@echo "  make dash     -- interactive dashboard on http://localhost:8050"
	@echo "  make dagster  -- orchestration UI on http://localhost:3000"
	@echo "  make docs     -- dbt lineage and docs on http://localhost:8080"

.PHONY: demo-anomalies
demo-anomalies: ## Same, with defects planted -- the quality tests should fire
	$(PYTHON) -m ingestion.generate --scale $(SCALE) --seed $(SEED) --inject-anomalies
	-cd $(WAREHOUSE) && ../$(DBT) build --full-refresh
	@echo
	@echo "Expected: several detector WARNINGS plus one ERROR from"
	@echo "assert_reject_rate_within_threshold -- and every model still built,"
	@echo "because the quarantine layer absorbed the bad rows."
	@echo "Inspect what was caught:"
	@echo "  marts.agg_data_quality  (grouped by reject_reason)"

# ---------------------------------------------------------------------------- #
# Pipeline stages
# ---------------------------------------------------------------------------- #

.PHONY: generate
generate: ## Generate the synthetic landing zone (SCALE=small)
	$(PYTHON) -m ingestion.generate --scale $(SCALE) --seed $(SEED)

# Keeps incremental state. Correct for repeated builds over one landing zone;
# after a fresh `make generate` use `rebuild` instead -- see the note on `demo`.
.PHONY: build
build: ## Run dbt build (models + tests, keeping incremental state)
	cd $(WAREHOUSE) && ../$(DBT) build $(DBT_SELECT)

.PHONY: rebuild
rebuild: ## Full refresh, ignoring incremental state
	cd $(WAREHOUSE) && ../$(DBT) build --full-refresh $(DBT_SELECT)

.PHONY: test
test: ## Run dbt tests only
	cd $(WAREHOUSE) && ../$(DBT) test $(DBT_SELECT)

.PHONY: unit-test
unit-test: ## Run dbt unit tests (needs a prior build -- see below)
	# Unit tests read no data: the fixture rows replace the input entirely. They
	# do need the upstream relations to exist, because dbt introspects them to
	# resolve column types -- so this target requires `make build` to have run.
	# `dbt build` also runs them, in dependency order.
	cd $(WAREHOUSE) && ../$(DBT) test --select "test_type:unit"

.PHONY: freshness
freshness: ## Check source freshness
	cd $(WAREHOUSE) && ../$(DBT) source freshness

.PHONY: parse
parse: ## Re-parse the project, refreshing target/manifest.json
	cd $(WAREHOUSE) && ../$(DBT) parse --no-partial-parse

.PHONY: catalog-artifacts
catalog-artifacts: ## Write target/catalog.json (needed by the governance tools)
	cd $(WAREHOUSE) && ../$(DBT) docs generate --no-compile

# ---------------------------------------------------------------------------- #
# Governance
# ---------------------------------------------------------------------------- #

.PHONY: governance
governance: parse catalog-artifacts ## Check classifications, regenerate secure views + catalog
	$(PYTHON) -m governance.check_classification
	$(PYTHON) -m governance.check_layer_boundaries
	$(PYTHON) -m governance.generate_secure_views
	$(PYTHON) -m governance.build_catalog
	cd $(WAREHOUSE) && ../$(DBT) build --select 40_secure

.PHONY: governance-check
governance-check: parse catalog-artifacts ## CI: verify tags and generated views are current
	$(PYTHON) -m governance.check_classification
	$(PYTHON) -m governance.check_layer_boundaries
	$(PYTHON) -m governance.generate_secure_views --check --diff

.PHONY: roles
roles: ## Show one customer as each role sees them
	$(PYTHON) scripts/show_roles.py

# ---------------------------------------------------------------------------- #
# Applications
# ---------------------------------------------------------------------------- #

.PHONY: dash
dash: ## Run the Dash dashboard on :8050
	$(PYTHON) -m dashboard.app

.PHONY: dash-export
dash-export: ## Render the static dashboard for GitHub Pages
	$(PYTHON) -m dashboard.export

.PHONY: dagster
dagster: ## Run the Dagster UI on :3000
	DAGSTER_HOME=$(CURDIR)/orchestration/.dagster_home \
		$(VENV)/bin/dagster dev -m orchestration.definitions

.PHONY: docs
docs: catalog-artifacts ## Serve the dbt docs site on :8080
	cd $(WAREHOUSE) && ../$(DBT) docs serve --port 8080

# ---------------------------------------------------------------------------- #
# Quality
# ---------------------------------------------------------------------------- #

.PHONY: lint
lint: ## Lint Python and SQL
	$(VENV)/bin/ruff check ingestion governance dashboard orchestration tests scripts
	$(VENV)/bin/ruff format --check ingestion governance dashboard orchestration tests scripts
	# SQLFluff uses the dbt templater, so it resolves ref() and macros through dbt
	# itself and lints the SQL that is actually produced. That means it opens a dbt
	# connection, which is why TRADEFLOW_DUCKDB has to be set even though nothing
	# is queried.
	$(VENV)/bin/sqlfluff lint $(WAREHOUSE)/models $(WAREHOUSE)/tests

.PHONY: fix
fix: ## Auto-fix what can be auto-fixed
	$(VENV)/bin/ruff check --fix ingestion governance dashboard orchestration tests scripts
	$(VENV)/bin/ruff format ingestion governance dashboard orchestration tests scripts
	$(VENV)/bin/sqlfluff fix $(WAREHOUSE)/models $(WAREHOUSE)/tests

.PHONY: pytest
pytest: ## Run the Python test suite
	$(VENV)/bin/pytest tests -q

.PHONY: ci
ci: lint pytest generate build governance-check ## Everything CI runs, locally
	@echo "CI-equivalent checks passed."

# ---------------------------------------------------------------------------- #
# Housekeeping
# ---------------------------------------------------------------------------- #

.PHONY: clean
clean: ## Remove generated data, the warehouse and dbt artefacts
	rm -rf data $(WAREHOUSE)/target $(WAREHOUSE)/logs logs
	rm -rf .pytest_cache .ruff_cache dashboard/static_export
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

.PHONY: clean-all
clean-all: clean ## Also remove the venv and dbt packages
	rm -rf $(VENV) $(WAREHOUSE)/dbt_packages orchestration/.dagster_home

.PHONY: up
up: ## docker compose up: Dagster + Dash + a built warehouse
	docker compose -f docker/compose.yml up --build

.PHONY: down
down: ## docker compose down
	docker compose -f docker/compose.yml down -v
