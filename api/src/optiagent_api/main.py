from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import optiagent_api
from optiagent_api.routers import agent, benchmarks, datasets, projects, solve, system
from optiagent_api.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=optiagent_api.__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(system.router)
    app.include_router(solve.router)
    app.include_router(datasets.router)
    app.include_router(agent.router)
    app.include_router(benchmarks.router)
    app.include_router(projects.router)
    return app


app = create_app()
