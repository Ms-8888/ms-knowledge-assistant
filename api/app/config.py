from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dim: int = 384

    top_k: int = 4
    min_score: float = 0.28

    llm_backend: Literal["extractive", "anthropic", "claude-cli", "ollama"] = "extractive"
    llm_enabled: bool = True
    llm_daily_call_cap: int = 200
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    ollama_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen2.5:7b"

    admin_key: str | None = None
    low_confidence_below: float = 0.45

    ask_rate_limit_per_minute: int = 30
    auto_ingest: bool = False
    seed_dir: str = "/seed"


settings = Settings()
