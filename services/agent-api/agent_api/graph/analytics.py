"""Analytics agent: natural language -> read-only SQL over v_tickets (managers only)."""

import re

import structlog
from langchain_core.messages import AIMessage
from langgraph.types import Command

from agent_api.clients import call_tool, emit
from agent_api.core.llm import get_llm, token_usage
from agent_api.core.metrics import GUARDRAIL, TOKENS
from agent_api.graph.common import active, back_to_supervisor, entities
from agent_api.graph.state import AgentState
from agent_api.guardrails.sql_guard import check_sql

log = structlog.get_logger()

SQL_PROMPT = """PostgreSQL için TEK bir SELECT sorgusu yaz. Sadece şu tabloları kullan:
{schema}
intent değerleri: password_reset, account_locked, vpn_issue, email_issue, software_install,
hardware_issue, network_issue, access_request, printer_issue.
"Bu hafta" = created_at >= date_trunc('week', now()). Sadece SQL döndür, açıklama yazma."""

TOPICS = {"vpn": "vpn_issue", "e-posta": "email_issue", "outlook": "email_issue",
          "mail": "email_issue", "şifre": "password_reset", "parola": "password_reset",
          "kilit": "account_locked", "yazıcı": "printer_issue", "kurulum": "software_install",
          "yazılım": "software_install", "donanım": "hardware_issue", "internet": "network_issue",
          "ağ": "network_issue", "erişim": "access_request"}
PERIODS = {"bugün": "date_trunc('day', now())", "bu hafta": "date_trunc('week', now())",
           "bu ay": "date_trunc('month', now())", "geçen hafta": "now() - interval '14 days'",
           "son 30 gün": "now() - interval '30 days'", "geçen ay": "now() - interval '2 months'"}


def rule_sql(question: str, departments: list[str]) -> str:
    """Template SQL for common manager questions when no LLM is configured."""
    q = question.replace("İ", "i").lower()
    where = []
    for word, period in PERIODS.items():
        if word in q:
            where.append(f"created_at >= {period}")
            break
    for word, intent in TOPICS.items():
        if re.search(rf"\b{re.escape(word)}", q):
            where.append(f"intent = '{intent}'")
            break
    if departments:
        # Case-insensitive match; quotes stripped and the guard re-parses the SQL anyway.
        safe = departments[0].replace("'", "")
        where.append(f"department ILIKE '{safe}'")
    if "açık" in q:
        where.append("status IN ('open', 'in_progress', 'escalated')")
    if "kritik" in q:
        where.append("severity = 'critical'")
    cond = f" WHERE {' AND '.join(where)}" if where else ""
    if "ortalama" in q and ("süre" in q or "saat" in q):
        return ("SELECT round(avg(extract(epoch FROM resolved_at - created_at) / 3600)::numeric, 1)"
                f" AS ortalama_cozum_saati FROM v_tickets{cond}"
                f"{' AND' if cond else ' WHERE'} resolved_at IS NOT NULL")
    if "departman" in q and not departments:
        return (f"SELECT department, count(*) AS ticket_sayisi FROM v_tickets{cond} "
                "GROUP BY department ORDER BY ticket_sayisi DESC")
    if re.search(r"en çok|hangi tür|dağılım", q):
        return (f"SELECT intent, count(*) AS ticket_sayisi FROM v_tickets{cond} "
                "GROUP BY intent ORDER BY ticket_sayisi DESC")
    if "takım" in q or "ekip" in q:
        return (f"SELECT assigned_team, count(*) AS ticket_sayisi FROM v_tickets{cond} "
                "GROUP BY assigned_team ORDER BY ticket_sayisi DESC")
    return f"SELECT count(*) AS ticket_sayisi FROM v_tickets{cond}"


async def _llm_sql(question: str, schema: dict) -> tuple[str | None, int]:
    llm = get_llm()
    if llm is None:
        return None, 0
    schema_text = "\n".join(f"{t}({', '.join(cols)})" for t, cols in schema.items())
    out = await llm.ainvoke([("system", SQL_PROMPT.format(schema=schema_text)),
                             ("human", question)])
    return extract_sql(str(out.content)), token_usage(out)


def extract_sql(text: str) -> str:
    """Small models wrap the query in prose: prefer a fenced block, else start at SELECT/WITH."""
    if fenced := re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE):
        return fenced.group(1).strip()
    start = re.search(r"\b(SELECT|WITH)\b", text, re.IGNORECASE)
    return text[start.start():].strip() if start else text.strip()


def _table(result: dict, max_rows: int = 20) -> str:
    cols = result["columns"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in result["rows"][:max_rows]:
        lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    if result["row_count"] > max_rows:
        lines.append(f"\n_{result['row_count']} satırdan ilk {max_rows} gösteriliyor._")
    return "\n".join(lines)


async def analytics(state: AgentState) -> Command:
    role = state["role"]
    if role != "manager":
        GUARDRAIL.labels("unauthorized_sql").inc()
        emit({"type": "guardrail", "kind": "unauthorized_sql", "role": role})
        return back_to_supervisor(
            state, {"stage": "done", "outcome": "refused"},
            messages=[AIMessage(content="Ticket istatistiklerine yalnızca yönetici rolündeki "
                                        "kullanıcılar erişebilir.", name="analytics")])

    question = state["turn_text"]
    schema = await call_tool("analytics", role, "get_schema", {})
    sql, tokens = None, 0
    try:
        sql, tokens = await _llm_sql(question, schema)
    except Exception as exc:  # noqa: BLE001
        log.warning("analytics.llm_failed", error=str(exc))
    TOKENS.labels("analytics").inc(tokens)
    fallback = rule_sql(question, entities(active(state), "DEPARTMAN"))
    if sql and not (llm_check := check_sql(sql)).ok:
        # The LLM's query failed the guard: record it, answer with the template query instead.
        GUARDRAIL.labels("sql_guard").inc()
        emit({"type": "sql", "sql": sql, "ok": False, "reason": llm_check.reason})
        sql = None
    sql = sql or fallback

    check = check_sql(sql)
    emit({"type": "sql", "sql": sql, "ok": check.ok, "reason": check.reason})
    if not check.ok:
        GUARDRAIL.labels("sql_guard").inc()
        return back_to_supervisor(
            state, {"stage": "done", "outcome": "refused"},
            messages=[AIMessage(content=f"Bu sorgu güvenlik kontrolünden geçmedi "
                                        f"({check.reason}).", name="analytics")])

    result = await call_tool("analytics", role, "run_sql", {"query": check.sql})
    if result["row_count"] == 1 and len(result["columns"]) == 1:
        value = next(iter(result["rows"][0].values()))
        summary = f"Sonuç: **{value}**"
    else:
        summary = f"{result['row_count']} satır bulundu."
    text = f"{summary}\n\n{_table(result)}\n\n```sql\n{check.sql}\n```"
    return back_to_supervisor(
        state, {"stage": "done", "outcome": "answered"},
        analytics={"sql": check.sql, "row_count": result["row_count"]},
        tokens=state.get("tokens", 0) + tokens,
        messages=[AIMessage(content=text, name="analytics")])
