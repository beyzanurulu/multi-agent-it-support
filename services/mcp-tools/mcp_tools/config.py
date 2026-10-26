from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/helpdesk"
    readonly_database_url: str = (
        "postgresql://helpdesk_readonly:readonly@localhost:5432/helpdesk"
    )
    # "fastembed" (multilingual MiniLM, production) or "hashing" (offline, tests/CI)
    embedding_provider: str = "fastembed"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    sql_row_limit: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()
