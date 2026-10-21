# Multi-Agent IT Support

LangGraph tabanlı, Supervisor + Triage / Solution / Ticket ajanlarından oluşan
IT destek otomasyonu. Detaylı plan: [project2-multi-agent-plan.md](project2-multi-agent-plan.md).

## Durum
- [x] Hafta 1 — Ajan iskeleti: `AgentState`, supervisor routing, triage (few-shot LLM +
  keyword fallback), StateGraph conditional edges, loop guard, LangSmith tracing
- [x] Hafta 2 — FastMCP tool server (6 tool), ChromaDB RAG (54 doküman), solution + ticket ajanları
- [x] Hafta 3 — Human-in-the-loop (kritik eskalasyon onayı), Guardrails AI doğrulama, SQLite checkpointer
- [ ] Hafta 4 — FastAPI WebSocket, Gradio, Docker, CI

## Akış
```
START → supervisor ─┬─> triage ───┐
                    ├─> solution ─┤ (her ajan supervisor'a döner)
                    ├─> ticket ───┘
                    └─> END
```
Kritik öncelik veya insan talebi → doğrudan ticket. Çözüm önerildikten sonra graph kullanıcı
geri bildirimini bekler; olumsuz geri bildirim ticket açtırır. `MAX_ITERATIONS` (varsayılan 10)
aşılırsa graceful çıkış.

## Çalıştırma
```bash
uv sync
cp .env.example .env   # OPENAI_API_KEY boşsa keyword sınıflandırıcı kullanılır
uv run python -m src.main
uv run pytest
```
