# OptiAgent

Natural language to **verified** optimization. OptiAgent turns a plain-English planning problem plus
your tabular data into a linear or mixed-integer program, solves it with OR-Tools, audits the
formulation for the mistakes LLMs actually make, and explains the result and its sensitivities.

The LLM never produces the final numbers.

## Repository layout

```
core/    optiagent_core   – deterministic engine: schema, model builder, solver, checks, analysis
agent/   optiagent_agent  – LLM pipeline (Ollama): extraction, clarification, audit, explanation
api/     optiagent_api    – FastAPI service
web/                      – Next.js + TypeScript + Tailwind + shadcn/ui frontend
```

`core` has no LLM or web dependencies, so it can be tested on its own.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 automatically)
- Node 24 and pnpm
- [Ollama](https://ollama.com) running locally
- Docker Desktop (for Postgres and Redis, or to run the whole stack)

## Running locally

```bash
cp .env.example .env

# Backing services
docker compose up -d postgres redis

# API  → http://localhost:8000/docs
uv sync
uv run uvicorn optiagent_api.main:app --reload

# Web  → http://localhost:3000
cd web
pnpm install
pnpm dev
```

Or run the whole stack in containers:

```bash
docker compose up --build
```

Ollama stays on the host; the API container reaches it through `host.docker.internal`.

## Checks

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
cd web && pnpm lint && pnpm typecheck && pnpm build
```

CI runs the same checks on every push.

## Roadmap

| Phase | Deliverable | Done when |
|---|---|---|
| 0 | Foundations: monorepo, API, web shell, Docker, CI | `docker compose up` runs everything; CI green |
| 1 | Solver engine: schema, builder, GLOP solve, solution checks | 5 hand-written instances solve correctly |
| 2 | Data ingestion and first UI | Upload → map → solve → flow diagram, no LLM |
| 3 | LLM extraction, clarification, human confirmation | 20 problems run end to end |
| 4 | Formulation audit | Catches most injected errors |
| 5 | Sensitivity, infeasibility diagnosis, grounded explanation | Duals match a manual calculation |
| 6 | Benchmarks, baselines, failure analysis | Results table and error distribution |
| 7 | Auth, projects, PDF export, real-data demo, deploy | A real user runs it on their own data |
| 8 | v2: MILP with fixed costs, CP-SAT rostering | — |
