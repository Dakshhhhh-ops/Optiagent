"""Choose and check the LLM provider from configuration."""

from __future__ import annotations

from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from optiagent_agent.llm import LLM, OllamaLLM, OpenAICompatibleLLM
from optiagent_agent.ollama import OllamaClient

Provider = Literal["ollama", "openai"]


class LLMConfig(BaseModel):
    provider: Provider = "ollama"
    base_url: str
    model: str
    api_key: SecretStr | None = None
    timeout: float = 120.0


class LLMStatus(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    provider: Provider
    base_url: str
    model: str
    reachable: bool
    model_available: bool = False
    models: list[str] = Field(default_factory=list)
    """A sample of the models the provider offers (at most 50)."""
    error: str | None = None


def make_llm(config: LLMConfig) -> LLM:
    if config.provider == "ollama":
        return OllamaLLM(config.base_url, config.model, timeout=max(config.timeout, 600.0))
    return OpenAICompatibleLLM(
        config.base_url,
        config.model,
        api_key=config.api_key.get_secret_value() if config.api_key else None,
        timeout=config.timeout,
    )


async def llm_status(config: LLMConfig, timeout: float = 5.0) -> LLMStatus:
    status = LLMStatus(
        provider=config.provider, base_url=config.base_url, model=config.model, reachable=False
    )
    if config.provider == "ollama":
        o = await OllamaClient(config.base_url, config.model, timeout=timeout).status()
        status.reachable = o.reachable
        status.models = o.models[:50]
        status.model_available = o.configured_model_available
        status.error = o.error or (
            None if o.configured_model_available or not o.reachable
            else f"model not downloaded (run: ollama pull {config.model})"
        )  # fmt: skip
        return status

    headers = (
        {"Authorization": f"Bearer {config.api_key.get_secret_value()}"} if config.api_key else {}
    )
    try:
        async with httpx.AsyncClient(base_url=config.base_url.rstrip("/"), timeout=timeout) as c:
            response = await c.get("/models", headers=headers)
    except httpx.HTTPError as exc:
        status.error = f"could not reach {config.base_url}: {exc}"
        return status
    if response.status_code == 401:
        status.error = "the provider rejected the API key"
        return status
    if response.is_error:
        status.error = f"provider returned {response.status_code}"
        return status
    status.reachable = True
    ids = [m.get("id", "") for m in response.json().get("data", []) if isinstance(m, dict)]
    status.models = ids[:50]
    status.model_available = config.model in ids
    if not status.model_available:
        status.error = f"model {config.model!r} is not offered by this provider"
    return status
