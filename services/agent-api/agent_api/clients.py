"""Clients for the NLU service and the FastMCP tool server.

Both accept "inprocess" as URL (tests, single-process dev): the other service's
package is imported directly instead of going over HTTP.
"""

import time

import httpx
from fastmcp import Client
from langgraph.config import get_stream_writer

from agent_api.core.config import get_settings
from agent_api.core.metrics import TOOL_CALLS
from agent_api.guardrails.limits import check_tool


def emit(event: dict) -> None:
    """Send a UI event (tool call, NLU output...) on the 'custom' stream, if any."""
    try:
        get_stream_writer()(event)
    except RuntimeError:  # called outside a graph run
        pass


NLU_MAX_CHARS = 2000  # nlu-service rejects longer input; the issue is stated up front anyway


async def analyze_text(text: str) -> dict:
    text = text[:NLU_MAX_CHARS]
    url = get_settings().nlu_url
    if url == "inprocess":
        from nlu_service.main import BACKEND, BACKEND_NAME

        return {**BACKEND.analyze(text), "backend": BACKEND_NAME}
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.post(f"{url}/nlu", json={"text": text})
        resp.raise_for_status()
        return resp.json()


def _transport():
    url = get_settings().mcp_url
    if url == "inprocess":
        from mcp_tools.server import mcp

        return mcp
    return url


async def call_tool(agent: str, role: str, tool: str, args: dict):
    """Allowlist-checked MCP tool call; returns the tool's structured result."""
    check_tool(agent, role, tool)
    started = time.perf_counter()
    try:
        async with Client(_transport()) as client:
            result = await client.call_tool(tool, args)
    except Exception as exc:
        TOOL_CALLS.labels(tool, "error").inc()
        emit({"type": "tool_call", "agent": agent, "tool": tool, "args": args, "ok": False,
              "error": str(exc)})
        raise
    TOOL_CALLS.labels(tool, "ok").inc()
    data = result.structured_content
    if isinstance(data, dict) and set(data) == {"result"}:
        data = data["result"]
    emit({"type": "tool_call", "agent": agent, "tool": tool, "args": args, "ok": True,
          "ms": round((time.perf_counter() - started) * 1000, 1)})
    return data
