"""Chainlit UI: chat with the agents and watch every step (NER, plan, tools, SQL) live.

    AGENT_API_URL=http://localhost:8000 chainlit run services/ui/chainlit_app.py
Demo accounts: calisan / uzman / yonetici (password from DEMO_PASSWORD, default "demo").
"""

import json
import os
import uuid

import chainlit as cl
import httpx
import websockets

API = os.getenv("AGENT_API_URL", "http://localhost:8000")
WS = API.replace("http", "ws", 1)
ROLE_TR = {"employee": "Çalışan", "it_specialist": "IT Uzmanı", "manager": "Yönetici"}
EXAMPLES = {
    "employee": ["Outlook açılmıyor 0x800CCC0E hatası veriyor, ayrıca VPN de bağlanmıyor.",
                 "Yazıcı kağıt sıkıştırıyor", "Talebimin durumu ne?"],
    "it_specialist": ["Tüm ofiste internet yok, kimse çalışamıyor", "Hesabım kilitlendi"],
    "manager": ["Bu hafta muhasebeden kaç VPN ticket'ı geldi?",
                "Departmanlara göre ticket dağılımını raporla", "Ortalama çözüm süresi kaç saat?"],
}
AGENT_TR = {"triage": "Triage", "solution": "Solution", "ticket": "Ticket",
            "analytics": "Analytics", "supervisor": "Supervisor", "guardrail": "Guardrail"}


@cl.password_auth_callback
async def auth(username: str, password: str) -> cl.User | None:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f"{API}/auth/login", json={"user_id": username, "password": password})
    if r.status_code != 200:
        return None
    data = r.json()
    return cl.User(identifier=username, metadata={"token": data["token"], "role": data["role"],
                                                  "department": data["department"]})


@cl.on_chat_start
async def start():
    user = cl.user_session.get("user")
    cl.user_session.set("session_id", str(uuid.uuid4()))
    role = user.metadata["role"]
    examples = "\n".join(f"- {e}" for e in EXAMPLES[role])
    await cl.Message(
        content=f"Merhaba! **{ROLE_TR[role]}** rolüyle giriş yaptınız "
                f"({user.metadata.get('department') or '-'}).\n\nÖrnek talepler:\n{examples}",
        author="Supervisor").send()


def _nlu_markdown(event: dict) -> str:
    intents = ", ".join(f"`{i['label']}` ({i['score']:.2f})" for i in event["intents"])
    ents = "\n".join(f"| {e['label']} | {e['text']} |" for e in event["entities"]) or "| - | - |"
    return (f"**Backend:** {event.get('backend', '?')}\n\n**Niyet:** {intents}\n\n"
            f"| Etiket | Değer |\n|---|---|\n{ents}")


async def _render(event: dict) -> dict | None:
    """Show one streamed event; returns the event if it is an approval request."""
    kind = event["type"]
    if kind == "nlu":
        async with cl.Step(name="NLU (intent + NER)", type="llm") as step:
            step.output = _nlu_markdown(event)
    elif kind == "plan":
        async with cl.Step(name="Supervisor planı", type="run") as step:
            step.output = "\n".join(f"{s['id']}. `{s['intent']}` → {s['agent']}"
                                    + (f" — {s['note']}" if s.get("note") else "")
                                    for s in event["steps"])
    elif kind == "plan_revision":
        async with cl.Step(name="Plan revizyonu", type="run") as step:
            step.output = f"Adım {event['step']}: {event['change']}"
    elif kind == "route":
        async with cl.Step(name=f"→ {AGENT_TR.get(event['agent'], event['agent'])} Agent",
                           type="run") as step:
            step.output = f"Adım {event['step']} (`{event['intent']}`) — plan: {event['plan']}"
    elif kind == "triage":
        async with cl.Step(name="Triage sonucu", type="run") as step:
            step.output = f"Öncelik: **{event['severity']}** {event.get('note') or ''}"
    elif kind == "tool_call":
        async with cl.Step(name=f"🔧 {event['tool']}", type="tool") as step:
            step.input = json.dumps(event["args"], ensure_ascii=False)
            step.output = "ok" if event["ok"] else f"hata: {event.get('error')}"
    elif kind == "sql":
        async with cl.Step(name="SQL guard", type="tool") as step:
            step.input = event["sql"]
            step.output = "geçti" if event["ok"] else f"engellendi: {event['reason']}"
    elif kind == "guardrail":
        async with cl.Step(name=f"🛡️ Guardrail: {event['kind']}", type="run") as step:
            step.output = json.dumps({k: v for k, v in event.items() if k != "type"},
                                     ensure_ascii=False)
    elif kind == "message":
        await cl.Message(content=event["content"],
                         author=AGENT_TR.get(event["agent"], event["agent"] or "Asistan")).send()
    elif kind == "interrupt":
        return event
    elif kind == "error":
        await cl.Message(content=f"⚠️ {event['detail']}", author="Sistem").send()
    return None


async def _ask_approval(event: dict) -> bool:
    d = event["draft"]
    text = (f"**{event['question']}**\n\n| Alan | Değer |\n|---|---|\n| Başlık | {d['title']} |\n"
            f"| Öncelik | {d['severity']}{' (L2 eskalasyon)' if event.get('escalate') else ''} |\n"
            f"| Kategori | {d['category']} |\n\n```\n{d['description']}\n```")
    res = await cl.AskActionMessage(content=text, author="Ticket", timeout=600, actions=[
        cl.Action(name="approve", payload={"approved": True}, label="✅ Onayla"),
        cl.Action(name="reject", payload={"approved": False}, label="❌ Reddet"),
    ]).send()
    return bool(res and res.get("payload", {}).get("approved"))


@cl.on_message
async def on_message(message: cl.Message):
    user = cl.user_session.get("user")
    url = f"{WS}/ws/chat/{cl.user_session.get('session_id')}?token={user.metadata['token']}"
    async with websockets.connect(url, max_size=2**22) as ws:
        await ws.send(json.dumps({"message": message.content}))
        while True:
            event = json.loads(await ws.recv())
            if event["type"] == "done":
                break
            pending = await _render(event)
            if pending:
                approved = await _ask_approval(pending)
                await ws.send(json.dumps({"type": "approval", "approved": approved}))
