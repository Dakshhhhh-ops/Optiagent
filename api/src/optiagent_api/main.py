from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import optiagent_api
from optiagent_api.db import get_engine, migrate
from optiagent_api.observability import (
    RequestContextMiddleware,
    configure_logging,
    install_error_handler,
)
from optiagent_api.routers import agent, benchmarks, datasets, projects, solve, system
from optiagent_api.security import SecurityMiddleware
from optiagent_api.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    migrate(get_engine(get_settings().database_url))
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    app = FastAPI(title=settings.app_name, version=optiagent_api.__version__, lifespan=lifespan)
    install_error_handler(app)
    # Middleware runs in reverse order of registration: request context wraps everything.
    app.add_middleware(SecurityMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(system.router)
    app.include_router(solve.router)
    app.include_router(datasets.router)
    app.include_router(agent.router)
    app.include_router(benchmarks.router)
    app.include_router(projects.router)
    return app


app = create_app()
