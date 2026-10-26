"""Short-term memory: LangGraph Postgres checkpointer (conversation state per thread)."""

from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


@asynccontextmanager
async def postgres_pool(url: str):
    pool = AsyncConnectionPool(url, min_size=1, max_size=10, open=False,
                               kwargs={"autocommit": True, "prepare_threshold": 0,
                                       "row_factory": dict_row})
    await pool.open()
    try:
        yield pool
    finally:
        await pool.close()


async def make_checkpointer(pool) -> AsyncPostgresSaver:
    saver = AsyncPostgresSaver(pool)
    await saver.setup()
    return saver
