FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Install dependencies first so source edits don't bust the cache.
COPY pyproject.toml uv.lock .python-version ./
COPY core/pyproject.toml core/pyproject.toml
COPY agent/pyproject.toml agent/pyproject.toml
COPY api/pyproject.toml api/pyproject.toml
RUN mkdir -p core/src/optiagent_core agent/src/optiagent_agent api/src/optiagent_api \
    && uv sync --frozen --no-dev --no-install-workspace

COPY core core
COPY agent agent
COPY api api
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "optiagent_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
