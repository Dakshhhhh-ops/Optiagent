from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPTIAGENT_", env_file=".env", extra="ignore")

    app_name: str = "OptiAgent API"
    cors_origins: list[str] = ["http://localhost:3000"]

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    redis_host: str = "localhost"
    redis_port: int = 6379

    upload_dir: Path = Path("uploads")
    database_path: Path = Path("data/optiagent.db")
    max_upload_bytes: int = 10_000_000
    max_upload_files: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
