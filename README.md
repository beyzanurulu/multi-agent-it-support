# Türkçe IT Destek Multi-Agent Platformu

Şirket çalışanının Türkçe yazdığı IT sorununu anlayan (intent + NER), planlayan, bilgi
tabanından çözen, gerekirse onay alarak ticket açan ve yöneticiye ticket istatistiklerini SQL
ile raporlayan multi-agent sistem. Plan: [project2-multi-agent-plan.md](project2-multi-agent-plan.md).

> Tüm kullanıcılar, ticketlar ve dokümanlar **sentetiktir**; gerçek kişi veya şirket verisi yoktur.

## Mimari (2 dakikada)

```
 Chainlit UI ──WebSocket──▶ agent-api (FastAPI + LangGraph)
                              │ limit → PII maskeleme → injection guard
                              │ NLU ──HTTP──▶ nlu-service (BERTurk ONNX / kural tabanlı)
                              │ SUPERVISOR (plan-and-execute)
                              │   ├─ Triage    öncelik, servis durumu, eksik bilgi
                              │   ├─ Solution  hibrit KB arama, kaynaklı çözüm
                              │   ├─ Ticket    interrupt() onayı → aç / eskale et
                              │   └─ Analytics yalnızca yönetici, NL→SQL (read-only)
                              │ tools ──HTTP──▶ mcp-tools (FastMCP, 8 tool)
                              ▼
                     PostgreSQL + pgvector (ticket, kullanıcı, KB, audit, checkpoint, memory)
```

Örnek: *"Outlook açılmıyor 0x800CCC0E hatası veriyor, ayrıca VPN de bağlanmıyor. Muhasebe
departmanındayım."*

1. NLU → `email_issue` + `vpn_issue`; `YAZILIM=Outlook`, `HATA_KODU=0x800CCC0E`, `YAZILIM=VPN`,
   `DEPARTMAN=Muhasebe`
2. Supervisor planı: **önce VPN** (Outlook'u etkileyebilir), sonra Outlook
3. Solution VPN için KB makalesini kaynağıyla verir → kullanıcı "olmadı" der
4. Ticket ajanı taslağı gösterir, **onay** bekler → ticket açılır, aynı turda Outlook adımına
   geçilir; hata koduyla `outlook_0x800ccc0e` makalesi bulunur
5. Yönetici: *"Bu hafta muhasebeden kaç VPN ticket'ı geldi?"* → Analytics güvenli SQL üretir,
   tablo + sorguyu döner

Ayrıntılar: [docs/architecture.md](docs/architecture.md) · Kararlar: [docs/adr/](docs/adr/)

## Durum

| Plan maddesi | Durum | Kanıt |
|---|---|---|
| 5 ajan, plan-and-execute, `Command` handoff, `interrupt` | ✅ | `services/agent-api/agent_api/graph/`, `tests/test_graph.py` |
| FastMCP tool server (8 tool, HTTP) | ✅ | `services/mcp-tools/`, `tests/test_tools.py` |
| PostgreSQL şema (alembic) + 500 sentetik ticket + pgvector KB (64 doküman) | ✅ | `db/` |
| Kısa (Postgres checkpointer) + uzun dönem (Postgres Store) hafıza | ✅ | `agent_api/memory/` |
| Guardrail'ler: injection, PII (Presidio), SQL guard, rol allowlist, adım/mesaj/token limiti, kaynak zorunluluğu | ✅ | `agent_api/guardrails/`, `tests/test_guardrails.py` |
| NLU servisi (ONNX Runtime) + kural tabanlı yedek | ✅ | `services/nlu-service/` |
| ML hattı: sentetik veri → temizlik → Label Studio → split → eğitim (MLflow) → ONNX → eval | ✅ kod, CI'da duman testi | `ml/`, `ml/tests/test_pipeline.py` |
| **BERTurk modelinin eğitilmesi ve metrikleri** | ⏳ GPU'da eğitilecek, 600 örnek elle doğrulanacak | [ml/MODEL_CARD.md](ml/MODEL_CARD.md) |
| 120 senaryolu eval + CI kapısı + belgelenmiş iterasyonlar | ✅ | [docs/eval-report.md](docs/eval-report.md) |
| Prometheus metrikleri + Grafana dashboard | ✅ | `deploy/monitoring/` |
| Chainlit arayüzü, 3 demo rolü | ✅ | `services/ui/` |
| Docker (arm64), k3s manifest'leri, GitHub Actions deploy | ✅ kod | `deploy/`, `.github/workflows/` |
| **Public URL** (Oracle Cloud k3s + Cloudflare) | ⏳ VM kurulumu ve secret'lar bekleniyor | aşağıda |

## Eval sonuçları (kural tabanlı NLU, LLM kapalı)

| Metrik | Hedef | Sonuç |
|---|---|---|
| Routing doğruluğu | ≥ %90 | %100 (baseline %90.8) |
| Görev başarısı | ≥ %85 | %100 (baseline %88.3) |
| Tool çağrı doğruluğu | ≥ %90 | %100 |
| Guardrail bloklama | %100 | %100 (baseline %92) |
| İlk yanıt p95 | < 3 sn | 78 ms (LLM çağrısı yok) |

Bu sayıların neyi kanıtlamadığı ve iterasyonların ayrıntısı: [docs/eval-report.md](docs/eval-report.md).

## Çalıştırma

### Docker Compose (önerilen)
```bash
cp .env.example .env            # OPENAI_API_KEY / LANGSMITH_* opsiyonel
docker compose up --build
```
- Arayüz: http://localhost:8080 — kullanıcılar `calisan`, `uzman`, `yonetici` (şifre `demo`)
- API dokümanı (OpenAPI): http://localhost:8000/docs
- Grafana: http://localhost:3000 · Prometheus: http://localhost:9090

### Geliştirme
```bash
uv sync --extra agent --extra mcp --extra nlu --extra db --extra ui
docker compose up -d postgres
uv run alembic -c db/alembic.ini upgrade head && uv run python db/seed/seed.py
uv run pytest -q services ml                         # 89 test
uv run python evals/run_eval.py --check              # 120 senaryo
```
Testler ve eval `EMBEDDING_PROVIDER=hashing` ile internet gerektirmeden çalışır.

### LLM
`OPENAI_API_KEY` varsa gpt-4o-mini; yoksa `OLLAMA_URL` ile yerel model; ikisi de yoksa ajanlar
kural tabanlı yollarla çalışır (KB makalesi adımları, şablon SQL).

## Canlıya alma (k3s)
1. Oracle Cloud Always Free Ampere VM'e k3s kurulumu (`curl -sfL https://get.k3s.io | sh -`).
2. `kubectl -n helpdesk create secret generic helpdesk-secrets --from-env-file=.env.prod`
   ([şablon](deploy/k8s/secrets.example.yaml)); Cloudflare Origin sertifikası →
   `cloudflare-origin` TLS secret'ı; `deploy/k8s/ingress.yaml` içindeki host'u güncelle.
3. GitHub → Settings → Secrets: `KUBECONFIG_B64`.
4. `main`'e push → CI → arm64 imajlar GHCR'a → `kubectl apply -k deploy/` → migrate job.

## Klasörler
```
services/agent-api   FastAPI + LangGraph (graph/, guardrails/, memory/, core/)
services/mcp-tools   FastMCP server + tools (kb, tickets, sql, users, status)
services/nlu-service /nlu (ONNX Runtime) + kural tabanlı yedek
services/ui          Chainlit
ml/                  veri üretimi, Label Studio, eğitim, ONNX export, değerlendirme, model kartı
db/                  alembic migration'ları, seed (kullanıcı, 500 ticket, 64 KB dokümanı)
evals/               120 senaryo, run_eval.py, raporlar
deploy/              k3s manifest'leri (kustomize), Prometheus/Grafana
docs/                mimari, ADR'ler, eval raporu
```
