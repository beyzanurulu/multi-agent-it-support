"""LLM access: OpenAI (cheap model) -> Ollama local fallback -> None (rule-based paths)."""

from functools import lru_cache

import structlog

from agent_api.core.config import get_settings

log = structlog.get_logger()


@lru_cache
def get_llm():
    s = get_settings()
    if s.openai_api_key:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=s.openai_model, api_key=s.openai_api_key, temperature=0)
    if s.ollama_url:
        from langchain_ollama import ChatOllama

        return ChatOllama(model=s.ollama_model, base_url=s.ollama_url, temperature=0)
    return None


def token_usage(message) -> int:
    usage = getattr(message, "usage_metadata", None) or {}
    return int(usage.get("total_tokens", 0))
