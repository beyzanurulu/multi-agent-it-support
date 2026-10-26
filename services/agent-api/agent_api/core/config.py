from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/helpdesk"
    nlu_url: str = "http://localhost:8002"  # "inprocess" -> import nlu_service directly
    mcp_url: str = "http://localhost:8001/mcp"  # "inprocess" -> import mcp_tools directly

    # LLM: OpenAI if a key is set, else Ollama if a URL is set, else rule-based fallbacks.
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    ollama_url: str = ""
    ollama_model: str = "qwen2.5:3b"

    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "multi-agent-it-support"

    auth_secret: str = "change-me"
    token_ttl_hours: int = 12
    # user_id:password pairs for the demo accounts (roles come from the users table)
    demo_accounts: str = "calisan:demo,uzman:demo,yonetici:demo"

    max_steps: int = 8
    recursion_limit: int = 40
    daily_message_limit: int = 50
    daily_token_budget: int = 2_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
