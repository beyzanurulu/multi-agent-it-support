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

    kb_path: str = "data/knowledge_base"
    chroma_path: str = ""  # empty -> in-memory ChromaDB
    kb_min_score: float = 0.15
    checkpoint_db: str = "checkpoints.sqlite"

    api_keys: str = ""  # comma separated; empty disables auth (local dev)
    rate_limit_per_minute: int = 30

    @property
    def api_key_set(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
