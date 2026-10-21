# Multi-Agent IT Support

LangGraph tabanlı, kurumsal IT destek otomasyonu: gelen talebi sınıflandıran, bilgi
tabanından çözüm öneren, gerektiğinde ticket açan ve kritik işlemlerde insan onayı bekleyen
çok ajanlı sistem. Detaylı plan: [project2-multi-agent-plan.md](project2-multi-agent-plan.md).

## Mimari

```
Kullanıcı ── REST / WebSocket ──► FastAPI Gateway (API key auth · rate limit · session)
                                        │
                                        ▼
                         ┌──────── SUPERVISOR ────────┐   loop guard (MAX_ITERATIONS)
                         │   routing · feedback       │   SQLite checkpointer
         ┌───────────────┼───────────────┬────────────┴──────────┐
         ▼               ▼               ▼                       ▼
     TRIAGE          SOLUTION         TICKET              HUMAN APPROVAL
  intent/severity   RAG + status    create/escalate      interrupt() — kritik
  (few-shot LLM +   Guardrails AI   notify · VIP bump    eskalasyon onayı
   keyword)         çıktı doğrulama  payload doğrulama
         └───────────────┴───────┬───────┴───────────────────────┘
                                 ▼
                 FastMCP tool server (6 tool)
     search_knowledge_base · create_ticket · check_system_status
     get_user_info · escalate_ticket · send_notification
                │                         │
           ChromaDB (54 KB dokümanı)   Mock CRM (in-memory)
```

Her ajan işini bitirince supervisor'a döner; supervisor bir sonraki adımı seçer:

| Durum | Sonraki ajan |
|---|---|
| Intent yok | triage |
| Kritik ve henüz onay yok | human_approval |
| Kritik (onaylı) / insan talebi / sınıflandırılamadı / servis kesintisi / KB'de cevap yok | ticket |
| Çözüm önerilmedi | solution |
| Çözüm önerildi, geri bildirim bekleniyor | END (kullanıcıyı bekle) |
| Çözüm reddedildi | ticket |
| Ticket açıldı / çözüm kabul edildi / iterasyon limiti | END |

## Özellikler
- **Intent classification:** OpenAI anahtarı varsa GPT-4o-mini few-shot + structured output,
  yoksa veya hata olursa Türkçe/İngilizce keyword sınıflandırıcı.
- **RAG:** 54 markdown dokümanı ChromaDB'de. OpenAI anahtarı varsa `text-embedding-3-small`,
  yoksa ücretsiz/offline hashing embedding.
- **Human-in-the-loop:** kritik talepler `interrupt()` ile durur; operatör REST, WebSocket,
  Gradio veya CLI üzerinden onaylar/reddeder.
- **Guardrails:** Guardrails AI ile yıkıcı komut (`format c:`, `rm -rf` …) ve sır sızıntısı
  engelleme, ticket payload şema doğrulaması, max iterasyon koruması.
- **Memory:** `AsyncSqliteSaver` — konuşmalar yeniden başlatmadan sonra devam eder.
- **Observability:** LangSmith tracing (her node ayrı run) + structlog + `/admin/sessions/{id}/trace`.

## Çalıştırma

```bash
cp .env.example .env        # OPENAI_API_KEY / LANGSMITH_* opsiyonel
docker compose up --build   # API: http://localhost:8000/docs · Demo: http://localhost:7860
```

Lokal:
```bash
uv sync --extra demo
uv run uvicorn src.api.main:app --reload      # API
uv run python -m src.ui.gradio_app            # Gradio demo
uv run python -m src.main                     # CLI
uv run python -m src.tools.server             # FastMCP server (stdio)
uv run pytest                                 # testler
```

## API

| Endpoint | Açıklama |
|---|---|
| `POST /chat` | `{message, user_id, session_id?}` → yeni mesajlar, state özeti, bekleyen onay |
| `POST /chat/{session_id}/approval` | `{approved, note}` — bekleyen eskalasyonu sürdürür |
| `GET /chat/{session_id}` | Oturum durumu |
| `WS /ws/chat/{session_id}?api_key=…` | `{message, user_id}` veya `{type: "approval", approved}` gönder; her ajan adımı `agent_step`, onay `interrupt`, son durum `done` olarak akar |
| `GET /admin/tickets`, `/admin/notifications` | Mock CRM kayıtları |
| `GET /admin/sessions/{id}/trace` | Checkpoint geçmişi — hangi ajan hangi adımda çalıştı |

Tüm endpoint'ler `X-API-Key` header'ı ister (`API_KEYS` boşsa auth kapalı).

## Testler
- `test_graph.py` — routing tablosu, kabul/ret akışı, onay akışı, servis kesintisi, VIP, SQLite kalıcılık
- `test_tools.py` — 6 MCP tool, KB arama isabeti
- `test_guardrails.py` — yıkıcı komut / sır engelleme, payload doğrulama, loop guard
- `test_api.py` — REST, WebSocket stream, onay, auth, rate limit
- `test_scenarios.py` — 5 uçtan uca IT senaryosu + güvenlik senaryosu, %90+ routing doğruluğu

## Kapsam dışı (plan gereği)
Gerçek CRM, gerçek bildirim, multi-tenant, fine-tuned classifier. Rate limiter ve mock CRM
tek process içindir.
