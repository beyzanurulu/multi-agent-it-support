import logging
import os

import structlog

from agent_api.core.config import get_settings


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    structlog.configure(processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(ensure_ascii=False),
    ])


def setup_tracing() -> bool:
    """LangSmith picks tracing up from env; every graph node becomes its own run."""
    s = get_settings()
    enabled = s.langsmith_tracing and bool(s.langsmith_api_key)
    os.environ["LANGSMITH_TRACING"] = "true" if enabled else "false"
    if enabled:
        os.environ["LANGSMITH_API_KEY"] = s.langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = s.langsmith_project
    return enabled
