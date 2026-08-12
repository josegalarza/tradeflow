#!/usr/bin/env bash
# Container entrypoint. One image, several roles, selected by the command.
#
#   build     generate data and build the warehouse, then exit
#   dash      serve the dashboard        (:8050)
#   dagster   serve the orchestration UI (:3000)
#   shell     drop into bash
#
# `build` runs to completion and exits, which is what lets compose use it as an
# init container the long-running services depend on.
set -euo pipefail

SCALE="${TRADEFLOW_SCALE:-small}"
SEED="${TRADEFLOW_SEED:-42}"

build_warehouse() {
  echo "==> generating landing zone (scale=${SCALE}, seed=${SEED})"
  python -m ingestion.generate --scale "${SCALE}" --seed "${SEED}"

  echo "==> building warehouse"
  (cd warehouse && dbt build)

  echo "==> governance artefacts"
  (cd warehouse && dbt docs generate --no-compile)
  python -m governance.check_classification
  python -m governance.check_layer_boundaries
  python -m governance.build_catalog

  echo "==> done"
}

wait_for_warehouse() {
  # The services depend on the build container, but a bind-mounted volume can
  # still be empty on a cold start if someone runs a service directly. Waiting
  # beats crash-looping with a stack trace.
  local waited=0
  until [ -f "${TRADEFLOW_DUCKDB}" ]; do
    if [ "${waited}" -ge 300 ]; then
      echo "no warehouse at ${TRADEFLOW_DUCKDB} after 5 minutes." >&2
      echo "Run the 'build' service first: docker compose run --rm build" >&2
      exit 1
    fi
    echo "waiting for the warehouse to be built... (${waited}s)"
    sleep 5
    waited=$((waited + 5))
  done
}

case "${1:-dash}" in
  build)
    build_warehouse
    ;;
  dash)
    wait_for_warehouse
    echo "==> dashboard on http://localhost:8050"
    exec python -m dashboard.app
    ;;
  dagster)
    wait_for_warehouse
    echo "==> dagster on http://localhost:3000"
    exec dagster dev -m orchestration.definitions --host 0.0.0.0 --port 3000
    ;;
  shell)
    exec /bin/bash
    ;;
  *)
    # Anything else is run verbatim, so `docker run ... dbt test` works.
    exec "$@"
    ;;
esac
