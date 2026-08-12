# Multi-stage build. The intermediate stage compiles wheels; the runtime stage
# carries only what is needed to run, which keeps the image to a size worth
# pulling.

# --- builder ---------------------------------------------------------------- #
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Requirements are copied on their own first so that Docker's layer cache is
# invalidated by a dependency change, not by every source edit. Rebuilds after a
# model change then take seconds instead of minutes.
COPY requirements/ requirements/
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --quiet --upgrade pip \
    && /opt/venv/bin/pip install --quiet \
        -r requirements/base.txt \
        -r requirements/orchestration.txt \
        -r requirements/dashboard.txt

# --- runtime ---------------------------------------------------------------- #
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="tradeflow" \
      org.opencontainers.image.description="Local-first analytics engineering platform (dbt + DuckDB + Dagster + Dash)" \
      org.opencontainers.image.source="https://github.com/josegalarza/tradeflow" \
      org.opencontainers.image.licenses="MIT"

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TRADEFLOW_LANDING_PATH=/app/data/landing \
    TRADEFLOW_DUCKDB=/app/data/tradeflow.duckdb \
    DBT_PROFILES_DIR=/app/warehouse \
    DAGSTER_HOME=/app/.dagster_home

WORKDIR /app

# Not root. The container writes only to /app/data, and nothing here needs the
# privileges that come with being root inside a container.
RUN useradd --create-home --uid 1001 tradeflow \
    && mkdir -p /app/data /app/.dagster_home \
    && chown -R tradeflow:tradeflow /app

COPY --chown=tradeflow:tradeflow warehouse/ warehouse/
COPY --chown=tradeflow:tradeflow ingestion/ ingestion/
COPY --chown=tradeflow:tradeflow governance/ governance/
COPY --chown=tradeflow:tradeflow dashboard/ dashboard/
COPY --chown=tradeflow:tradeflow orchestration/ orchestration/
COPY --chown=tradeflow:tradeflow scripts/ scripts/
COPY --chown=tradeflow:tradeflow docker/entrypoint.sh /usr/local/bin/entrypoint

USER tradeflow

# dbt packages are installed at build time so the container starts without
# needing to reach the internet.
RUN cd warehouse && dbt deps

EXPOSE 3000 8050

ENTRYPOINT ["/usr/local/bin/entrypoint"]
CMD ["dash"]
