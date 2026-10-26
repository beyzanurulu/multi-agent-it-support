"""Step limit, per-agent/per-role tool allowlist, daily message and token budgets."""

from datetime import date

from agent_api.core.config import get_settings

# Which MCP tools each agent may call.
AGENT_TOOLS: dict[str, set[str]] = {
    "triage": {"get_user_info", "check_system_status"},
    "solution": {"search_kb"},
    "ticket": {"create_ticket", "escalate_ticket", "notify", "get_user_info"},
    "analytics": {"get_schema", "run_sql"},
}
# Which tools each user role may trigger at all.
ROLE_TOOLS: dict[str, set[str]] = {
    "employee": {"get_user_info", "check_system_status", "search_kb", "create_ticket", "notify"},
    "it_specialist": {"get_user_info", "check_system_status", "search_kb", "create_ticket",
                      "notify", "escalate_ticket"},
    "manager": {"get_user_info", "check_system_status", "search_kb", "create_ticket", "notify",
                "escalate_ticket", "get_schema", "run_sql"},
}
# Escalation is a side effect of creating a critical ticket, approved by the user.
IMPLICIT = {"escalate_ticket"}


class ToolNotAllowed(PermissionError):
    pass


def check_tool(agent: str, role: str, tool: str) -> None:
    if tool not in AGENT_TOOLS.get(agent, set()):
        raise ToolNotAllowed(f"agent '{agent}' may not call '{tool}'")
    if tool not in ROLE_TOOLS.get(role, set()) and tool not in IMPLICIT:
        raise ToolNotAllowed(f"role '{role}' may not call '{tool}'")


def step_limit_reached(step_count: int) -> bool:
    return step_count >= get_settings().max_steps


async def consume_message(pool, user_id: str) -> tuple[bool, str]:
    """Count one message; refuse when the user or the global token budget is exhausted."""
    s = get_settings()
    async with pool.connection() as conn:
        row = await (await conn.execute(
            "INSERT INTO usage_counters (day, user_id, messages) VALUES (%s, %s, 1) "
            "ON CONFLICT (day, user_id) DO UPDATE SET messages = usage_counters.messages + 1 "
            "RETURNING messages", (date.today(), user_id))).fetchone()
        tokens = (await (await conn.execute(
            "SELECT coalesce(sum(tokens), 0) AS t FROM usage_counters WHERE day = %s",
            (date.today(),))).fetchone())
    if row["messages"] > s.daily_message_limit:
        return False, "Günlük mesaj limitinize ulaştınız, yarın tekrar deneyin."
    if tokens["t"] >= s.daily_token_budget:
        return False, "Sistemin günlük kullanım bütçesi doldu, lütfen daha sonra deneyin."
    return True, ""


async def add_tokens(pool, user_id: str, tokens: int) -> None:
    if tokens <= 0:
        return
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO usage_counters (day, user_id, tokens) VALUES (%s, %s, %s) "
            "ON CONFLICT (day, user_id) DO UPDATE SET tokens = usage_counters.tokens + %s",
            (date.today(), user_id, tokens, tokens))
