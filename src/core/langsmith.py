"""LangSmith tracing setup.

LangChain/LangGraph pick tracing up from environment variables, so we only
need to export them once at startup. Each graph node then shows up as a
separate run in the LangSmith trace.
"""

import os

import structlog

from src.core.config import Settings, get_settings

log = structlog.get_logger()


def setup_tracing(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    if not (settings.langsmith_tracing and settings.langsmith_api_key):
        os.environ["LANGSMITH_TRACING"] = "false"
        log.info("langsmith.disabled")
        return False

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    log.info("langsmith.enabled", project=settings.langsmith_project)
    return True
