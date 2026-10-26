"""Postgres connection pools (read-write for tools, read-only for analytics SQL)."""

from functools import lru_cache

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from mcp_tools.config import get_settings


async def _configure(conn) -> None:
    conn.row_factory = dict_row


@lru_cache
def get_pool() -> AsyncConnectionPool:
    return AsyncConnectionPool(
        get_settings().database_url, min_size=1, max_size=5, open=False, configure=_configure
    )


@lru_cache
def get_readonly_pool() -> AsyncConnectionPool:
    return AsyncConnectionPool(
        get_settings().readonly_database_url, min_size=1, max_size=3, open=False,
        configure=_configure,
    )


_users = 0  # MCP sessions sharing the pools (in-process clients can overlap)


async def open_pools() -> None:
    global _users
    _users += 1
    if _users == 1:
        await get_pool().open()
        await get_readonly_pool().open()


async def close_pools() -> None:
    global _users
    _users -= 1
    if _users == 0:
        for pool in (get_pool(), get_readonly_pool()):
            await pool.close()
        get_pool.cache_clear()
        get_readonly_pool.cache_clear()
