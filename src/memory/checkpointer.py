"""SQLite-backed LangGraph checkpointer for persistent conversation memory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.core.config import get_settings


@asynccontextmanager
async def sqlite_checkpointer(path: str | None = None) -> AsyncIterator[AsyncSqliteSaver]:
    async with AsyncSqliteSaver.from_conn_string(path or get_settings().checkpoint_db) as saver:
        yield saver
