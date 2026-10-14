"""Thin async client for a local Ollama server."""

from __future__ import annotations

import httpx
from pydantic import BaseModel


class OllamaStatus(BaseModel):
    reachable: bool
    base_url: str
    models: list[str] = []
    configured_model: str
    configured_model_available: bool = False
    error: str | None = None


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.get("/api/tags")
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]

    async def status(self) -> OllamaStatus:
        try:
            models = await self.list_models()
        except httpx.HTTPError as exc:
            return OllamaStatus(
                reachable=False,
                base_url=self.base_url,
                configured_model=self.model,
                error=f"{type(exc).__name__}: {exc}",
            )
        return OllamaStatus(
            reachable=True,
            base_url=self.base_url,
            models=models,
            configured_model=self.model,
            configured_model_available=self.model in models,
        )
