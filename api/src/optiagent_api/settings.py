from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from optiagent_agent.providers import LLMConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPTIAGENT_", env_file=".env", extra="ignore")

    app_name: str = "OptiAgent API"
    cors_origins: list[str] = ["http://localhost:3000"]

    # LLM. "ollama" runs locally; "openai" is any OpenAI-compatible API (Groq, OpenRouter, ...).
    llm_provider: Literal["ollama", "openai"] = "ollama"
    llm_base_url: str = ""
    """Defaults to ollama_base_url for Ollama. For Groq: https://api.groq.com/openai/v1"""
    llm_model: str = ""
    """Defaults to ollama_model for Ollama."""
    llm_api_key: SecretStr | None = None
    llm_timeout: float = 120.0

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    redis_host: str = "localhost"
    redis_port: int = 6379

    database_url: str = "sqlite:///data/optiagent.db"
    """Local SQLite by default. In production a Postgres URL, e.g. from Neon."""
    max_upload_bytes: int = 10_000_000
    max_upload_files: int = 10

    # Authentication (Clerk). Leave unset for local single-user mode.
    auth_issuer: str | None = None
    """Clerk Frontend API URL, e.g. https://your-app.clerk.accounts.dev"""
    auth_authorized_parties: list[str] = []
    """Origins allowed in the token's azp claim. Defaults to cors_origins."""

    # Abuse and cost protection (in-memory, per API instance).
    trust_proxy: bool = False
    """Set true behind Render/Fly/etc. so the client IP is read from X-Forwarded-For."""
    requests_per_minute: int = 240
    """Per IP, all endpoints."""
    llm_requests_per_hour: int = 30
    """Per signed-in user (or IP), for endpoints that call the LLM."""
    llm_requests_per_day: int = 2_000
    """Across all users: caps the provider bill."""
    max_request_bytes: int = 40_000_000

    # Observability
    log_json: bool = False
    log_level: str = "info"
    sentry_dsn: SecretStr | None = None

    def llm_config(self) -> LLMConfig:
        if self.llm_provider == "ollama":
            return LLMConfig(
                provider="ollama",
                base_url=self.llm_base_url or self.ollama_base_url,
                model=self.llm_model or self.ollama_model,
                timeout=self.llm_timeout,
            )
        return LLMConfig(
            provider="openai",
            base_url=self.llm_base_url,
            model=self.llm_model,
            api_key=self.llm_api_key,
            timeout=self.llm_timeout,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
