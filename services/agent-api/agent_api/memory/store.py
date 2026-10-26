"""Long-term memory: LangGraph Postgres Store.

Namespace ("users", <user_id>, "issues") keeps one item per resolved issue or
ticket so triage can recognise repeat problems across conversations.
"""

from langgraph.store.postgres.aio import AsyncPostgresStore


async def make_store(pool) -> AsyncPostgresStore:
    store = AsyncPostgresStore(pool)
    await store.setup()
    return store
