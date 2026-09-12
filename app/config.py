from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://postgres:postgres@db:5432/copilot"
    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"
    llm_timeout_seconds: int = 30
    max_tool_iterations: int = 3
    app_env: str = "local"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
