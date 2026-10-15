FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Install dependencies first so source edits don't bust the cache.
COPY pyproject.toml uv.lock .python-version ./
COPY core/pyproject.toml core/pyproject.toml
COPY agent/pyproject.toml agent/pyproject.toml
COPY api/pyproject.toml api/pyproject.toml
COPY eval/pyproject.toml eval/pyproject.toml
RUN mkdir -p core/src/optiagent_core agent/src/optiagent_agent api/src/optiagent_api eval/src/optiagent_eval \
    && uv sync --frozen --no-dev --package optiagent-api --no-install-workspace

COPY core core
COPY agent agent
COPY api api
COPY eval eval
RUN uv sync --frozen --no-dev --package optiagent-api

ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 app && mkdir -p /app/data && chown -R app /app/data
USER app

EXPOSE 8000
# Hosts like Render pass the port in $PORT. --proxy-headers makes HTTPS detection and client IPs
# work behind their load balancer.
CMD ["sh", "-c", "uvicorn optiagent_api.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
