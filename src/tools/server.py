"""FastMCP tool server.

Runs standalone (`python -m src.tools.server`, stdio transport) for external
MCP clients, and in-process for the agents via `call_tool`.
"""

from fastmcp import Client, FastMCP

from src.tools.it_tools import ALL_TOOLS

mcp = FastMCP("it-support-tools")
for _tool in ALL_TOOLS:
    mcp.tool(_tool)


async def call_tool(name: str, arguments: dict):
    """Call a tool through the MCP protocol using an in-memory transport."""
    async with Client(mcp) as client:
        result = await client.call_tool(name, arguments)
    data = result.structured_content
    if isinstance(data, dict) and set(data) == {"result"}:
        return data["result"]
    return data


if __name__ == "__main__":
    mcp.run()
