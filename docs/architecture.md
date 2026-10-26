# Mimari

## Servisler

| Servis | Kod | Görev | Port |
|---|---|---|---|
| ui | `services/ui/chainlit_app.py` | Chainlit sohbet arayüzü, 3 demo rolü, ajan adımlarını gösterir | 8080 |
| agent-api | `services/agent-api/agent_api` | FastAPI + LangGraph: guardrail, supervisor, 4 ajan, auth, limitler, metrikler | 8000 |
| nlu-service | `services/nlu-service/nlu_service` | `/nlu`: çok etiketli intent + Türkçe NER (ONNX BERTurk, yoksa kural tabanlı) | 8002 |
| mcp-tools | `services/mcp-tools/mcp_tools` | FastMCP (streamable HTTP), 8 tool, Postgres + pgvector | 8001 |
| postgres | `db/` | ticket, kullanıcı, departman, audit, KB vektörleri, checkpoint, uzun dönem hafıza | 5432 |

Tek repo, tek `pyproject.toml`; her servis kendi extra'sını (`--extra agent|mcp|nlu|ui`) kurar.
Servisler birbirini yalnızca HTTP ile çağırır; testlerde `NLU_URL=inprocess`, `MCP_URL=inprocess`
ile aynı süreçte çalışırlar.

## Bir mesajın yolu

```
kullanıcı mesajı
  │  agent-api runner: günlük mesaj limiti / token bütçesi → PII maskeleme (Presidio)
  ▼
guard_in ── prompt injection → (blok) → END
  ▼
nlu ── nlu-service /nlu → intents[] + entities[]
  ▼
supervisor (plan-and-execute)
  • yeni talep → planner: niyetleri öncelik sırasına dizer (ağ/VPN önce)
  • çözüm geri bildirimi → plan revizyonu (çözüldü → sonraki adım, olmadı → ticket)
  • eksik bilgi cevabı → adımı triage'a geri gönderir
  • adım sınırı (8) → özetle çık
  │  Command(goto=<ajan>)
  ├─▶ triage    get_user_info, check_system_status, uzun dönem hafıza → öncelik / soru
  ├─▶ solution  search_kb (pgvector + Türkçe FTS + hata kodu, RRF) → kaynaklı adımlar
  ├─▶ ticket    interrupt() onayı → create_ticket (+ escalate_ticket) → notify
  └─▶ analytics yalnızca yönetici: get_schema → NL→SQL → SQL guard → run_sql (read-only)
        │  Command(goto="supervisor")
        ▼
  supervisor → sonraki adım / kullanıcı cevabını bekle (END)
```

## Ajanlar arası iletişim
- **Shared memory:** `AgentState` (plan, NLU çıktısı, ticketlar…) her adımda Postgres
  checkpointer'a yazılır; konuşma yeniden başlatmadan sonra kaldığı yerden devam eder.
- **Message passing:** her ajan `Command(goto="supervisor", update=...)` döner; supervisor
  `Command(goto=<ajan>)` ile iş verir. Graph'ta sabit kenar yalnızca giriştedir.
- **Tool usage:** ajanlar tool'lara yalnızca MCP üzerinden ulaşır; `limits.check_tool` ajan ×
  rol allowlist'ini her çağrıda uygular.

## Hafıza
- Kısa dönem: `AsyncPostgresSaver`, thread id = `<user_id>:<session_id>` (kullanıcılar birbirinin
  konuşmasını devam ettiremez).
- Uzun dönem: `AsyncPostgresStore`, namespace `("users", <id>, "issues")`; çözülen sorunlar ve
  açılan ticketlar. Triage tekrar eden sorunları buradan fark eder.

## Güvenlik katmanları
| Risk | Nerede |
|---|---|
| Prompt injection | `guardrails/injection.py` (giriş), yazma tool'ları ayrıca onaysız çalışmaz |
| PII | `guardrails/pii.py` — TC (checksum), telefon, e-posta, IBAN maskelenir; LLM/log/ticket maskeli metni görür |
| SQL | `guardrails/sql_guard.py` (sqlglot: tek SELECT, tablo allowlist, yasak fonksiyon, LIMIT ≤ 200) + `run_sql` read-only DB rolü (`v_tickets`/`departments` dışında yetki yok, 5 sn timeout) + alt sorgu sarmalama |
| Yetki | rol × ajan tool allowlist (`guardrails/limits.py`), Analytics yalnızca `manager` |
| Halüsinasyon | `SolutionAnswer` şeması en az bir KB kaynağı ister; kaynak id'si getirilen dokümanlar dışındaysa cevap reddedilir |
| Sonsuz döngü | supervisor adım sayacı (8) + LangGraph `recursion_limit` (40) |
| Maliyet | kullanıcı başına günlük mesaj limiti + global günlük token bütçesi (`usage_counters`) |

## İzleme
- LangSmith: `LANGSMITH_TRACING=true` iken her node ayrı run olarak izlenir.
- Prometheus (`/metrics/`): `agent_requests_total`, `agent_step_seconds`,
  `agent_first_response_seconds`, `agent_tool_calls_total`, `agent_llm_tokens_total`,
  `agent_guardrail_triggers_total`, `nlu_inference_seconds`.
- Grafana: `deploy/monitoring/grafana/dashboards/helpdesk.json`.

## Deploy
`git push main` → CI (lint + test + eval) → Deploy: arm64 imajlar (buildx/QEMU) → GHCR →
`kubectl apply -k deploy/` → migrate job → rollout. k3s, Oracle Cloud Always Free Ampere VM;
Traefik ingress, Cloudflare proxy + Origin Certificate.
