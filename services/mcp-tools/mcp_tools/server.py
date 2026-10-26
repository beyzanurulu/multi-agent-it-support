"""FastMCP tool server (separate service, streamable HTTP transport).

    python -m mcp_tools.server        # serves http://0.0.0.0:8001/mcp
"""

import os
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from mcp_tools.db import close_pools, open_pools
from mcp_tools.tools.kb import search_kb
from mcp_tools.tools.sql import get_schema, run_sql
from mcp_tools.tools.status import check_system_status
from mcp_tools.tools.tickets import create_ticket, escalate_ticket, notify
from mcp_tools.tools.users import get_user_info

TOOLS = [search_kb, create_ticket, escalate_ticket, notify, get_user_info,
         check_system_status, get_schema, run_sql]


@asynccontextmanager
async def lifespan(_server):
    await open_pools()
    try:
        yield
    finally:
        await close_pools()


mcp = FastMCP("it-support-tools", lifespan=lifespan)
for _tool in TOOLS:
    mcp.tool(_tool)


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=int(os.getenv("PORT", "8001")))
