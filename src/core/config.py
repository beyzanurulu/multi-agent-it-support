"""Application settings loaded from environment / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "multi-agent-it-support"

    max_iterations: int = 10

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
