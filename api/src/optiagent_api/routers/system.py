import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import optiagent_api
from optiagent_agent.ollama import OllamaClient, OllamaStatus
from optiagent_api.settings import Settings, get_settings

router = APIRouter(tags=["system"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


class ServiceStatus(BaseModel):
    name: str
    reachable: bool
    detail: str | None = None


class SystemStatus(BaseModel):
    version: str
    ollama: OllamaStatus
    services: list[ServiceStatus]


async def _tcp_check(name: str, host: str, port: int) -> ServiceStatus:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=2)
    except (OSError, TimeoutError) as exc:
        reason = str(exc) or type(exc).__name__
        return ServiceStatus(name=name, reachable=False, detail=f"{host}:{port} — {reason}")
    writer.close()
    await writer.wait_closed()
    return ServiceStatus(name=name, reachable=True, detail=f"{host}:{port}")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/v1/system/status", response_model=SystemStatus)
async def system_status(settings: SettingsDep) -> SystemStatus:
    ollama = OllamaClient(settings.ollama_base_url, settings.ollama_model)
    ollama_status, postgres, redis = await asyncio.gather(
        ollama.status(),
        _tcp_check("postgres", settings.postgres_host, settings.postgres_port),
        _tcp_check("redis", settings.redis_host, settings.redis_port),
    )
    return SystemStatus(
        version=optiagent_api.__version__,
        ollama=ollama_status,
        services=[postgres, redis],
    )
