"""Minimal Gradio chat demo talking to the FastAPI gateway over REST."""

import os
import uuid

import gradio as gr
import httpx

API_URL = os.getenv("API_URL", "http://localhost:8000")
API_KEY = os.getenv("DEMO_API_KEY", "dev-key")
DEMO_USERS = ["u001", "u002", "u003"]


def _post(path: str, payload: dict) -> dict:
    resp = httpx.post(f"{API_URL}{path}", json=payload, headers={"X-API-Key": API_KEY}, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _render(body: dict, history: list) -> tuple[list, str, dict]:
    for msg in body.get("new_messages", []):
        history.append({"role": "assistant", "content": f"**[{msg['agent']}]** {msg['content']}"})
    pending = body.get("pending_approval")
    approval = gr.update(visible=bool(pending))
    state = {k: v for k, v in body["state"].items() if v not in (None, "", [])}
    info = "\n".join(f"- **{k}**: {v}" for k, v in state.items())
    if pending:
        info += f"\n\n⚠️ **Operatör onayı bekleniyor:** {pending['question']}"
    return history, info, approval


def send(message: str, history: list, session_id: str, user_id: str):
    history = history + [{"role": "user", "content": message}]
    body = _post("/chat", {"message": message, "user_id": user_id, "session_id": session_id})
    return "", *_render(body, history)


def decide(approved: bool, history: list, session_id: str):
    body = _post(f"/chat/{session_id}/approval", {"approved": approved})
    return _render(body, history)


def new_session():
    return [], str(uuid.uuid4()), "", gr.update(visible=False)


with gr.Blocks(title="IT Destek Asistanı") as demo:
    gr.Markdown("# 🛠️ Multi-Agent IT Destek\nSupervisor → Triage → Solution / Ticket")
    session = gr.State(str(uuid.uuid4()))
    with gr.Row():
        with gr.Column(scale=3):
            chat = gr.Chatbot(height=480)
            box = gr.Textbox(placeholder="Sorununuzu yazın… (örn. VPN bağlanmıyor)", label="Mesaj")
            with gr.Row(visible=False) as approval_row:
                approve_btn = gr.Button("✅ Eskalasyonu onayla", variant="primary")
                reject_btn = gr.Button("❌ Reddet")
        with gr.Column(scale=1):
            user = gr.Dropdown(DEMO_USERS, value="u001", label="Kullanıcı (u002 = VIP)")
            info = gr.Markdown()
            gr.Button("Yeni oturum").click(new_session, None, [chat, session, info, approval_row])

    box.submit(send, [box, chat, session, user], [box, chat, info, approval_row])
    approve_btn.click(lambda h, s: decide(True, h, s), [chat, session], [chat, info, approval_row])
    reject_btn.click(lambda h, s: decide(False, h, s), [chat, session], [chat, info, approval_row])


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.getenv("PORT", "7860")))
