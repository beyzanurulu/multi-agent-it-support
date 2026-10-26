"""Read-only analytics SQL.

Protection is layered: the agent-side SQL guard (sqlglot) rejects anything but a
single SELECT on allowlisted tables; here the query runs as `helpdesk_readonly`
(SELECT on v_tickets/departments only, read-only transactions, 5 s timeout) and
is wrapped in a subquery so a row limit always applies.
"""

from mcp_tools.config import get_settings
from mcp_tools.db import get_pool, get_readonly_pool

ALLOWED_TABLES = ("v_tickets", "departments")


async def get_schema() -> dict:
    """Columns of the tables the analytics agent may query."""
    async with get_pool().connection() as conn:
        rows = await (await conn.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = ANY(%s) "
            "ORDER BY table_name, ordinal_position", (list(ALLOWED_TABLES),),
        )).fetchall()
    schema: dict[str, list[str]] = {}
    for r in rows:
        schema.setdefault(r["table_name"], []).append(f"{r['column_name']} {r['data_type']}")
    return schema


async def run_sql(query: str) -> dict:
    """Run a read-only SELECT (max 200 rows) against the analytics view."""
    limit = get_settings().sql_row_limit
    sql = query.strip().rstrip(";")
    wrapped = f"SELECT * FROM ({sql}) AS q LIMIT {limit}"
    async with get_readonly_pool().connection() as conn:
        cur = await conn.execute(wrapped)
        rows = await cur.fetchall()
        columns = [c.name for c in cur.description]
    return {"columns": columns,
            "rows": [{k: (v if isinstance(v, (int, float, str, bool, type(None))) else str(v))
                      for k, v in r.items()} for r in rows],
            "row_count": len(rows)}
