from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://postgres:postgres@db:5432/copilot"
    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    llm_base_url: str | None = None
    llm_model: str = "claude-sonnet-4-6"
    llm_timeout_seconds: int = 30
    max_tool_iterations: int = 3
    rate_limit_per_window: int = 20
    rate_limit_window_seconds: int = 60
    conversation_ttl_seconds: int = 1800
    conversation_max_messages: int = 8
    app_env: str = "local"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
