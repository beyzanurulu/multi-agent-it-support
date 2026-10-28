# Türkçe IT Destek Multi-Agent Platformu

Şirket çalışanının Türkçe yazdığı IT sorununu anlayan (intent + NER), planlayan, bilgi
tabanından çözen, gerekirse onay alarak ticket açan ve yöneticiye ticket istatistiklerini SQL
ile raporlayan multi-agent sistem.

> Tüm kullanıcılar, ticketlar ve dokümanlar **sentetiktir**; gerçek kişi veya şirket verisi yoktur.

## Mimari 

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

## Ekran görüntüleri

Yukarıdaki örnek, Chainlit arayüzünde (LLM kapalı, kural tabanlı NLU). Her adımın NLU çıktısı,
plan, tool çağrıları ve SQL'i arayüzde açılabilir.

| Plan + kaynaklı çözüm | Ticket onayı (`interrupt`) |
|---|---|
| ![Plan ve çözüm](docs/images/1-plan-ve-cozum.png) | ![Ticket onayı](docs/images/2-ticket-onayi.png) |
| **Ticket açıldı, sıradaki adıma geçildi** | **Yönetici: NL → güvenli SQL** |
| ![Ticket açıldı](docs/images/3-ticket-acildi.png) | ![Yönetici raporu](docs/images/4-yonetici-rapor.png) |
| **Prompt injection engellendi** | **Grafana: ajan metrikleri** |
| ![Guardrail](docs/images/5-guardrail.png) | ![Grafana](docs/images/6-grafana.png) |

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
| Docker Compose ile uçtan uca yerel çalıştırma + 55 uç senaryo | ✅ | [evals/e2e_edge_cases.py](evals/e2e_edge_cases.py) (54/55; 1 bilinen NLU sınırı) |
| arm64 imajlar, k3s manifest'leri, GitHub Actions deploy | ✅ kod, gerçek kümede denenmedi | `deploy/`, `.github/workflows/` |
| Public erişim (Cloudflare Tunnel) | ✅ geçici link ile denendi; kalıcı sunucu ⏳ | [Canlıya alma](#canlıya-alma) |

## Eval sonuçları (kural tabanlı NLU, LLM kapalı)

| Metrik | Hedef | Sonuç |
|---|---|---|
| Routing doğruluğu | ≥ %90 | %100 (baseline %90.8) |
| Görev başarısı | ≥ %85 | %100 (baseline %88.3) |
| Tool çağrı doğruluğu | ≥ %90 | %100 |
| Guardrail bloklama | %100 | %100 (baseline %92) |
| İlk yanıt p95 | < 3 sn | 78 ms (LLM çağrısı yok) |

LLM açık pilot (yerel Ollama `qwen2.5:7b`, 14 senaryo): 14/14, ilk yanıt p95 22.7 sn —
hızlı barındırılan modelle tam tur ⏳.

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
uv run pytest -q services ml                         # birim + entegrasyon testleri
uv run python evals/run_eval.py --check              # 120 senaryo (CI kapısı)
uv run python evals/e2e_edge_cases.py                # 55 uç senaryo, compose ayaktayken
```
Testler ve eval `EMBEDDING_PROVIDER=hashing` ile internet gerektirmeden çalışır. Veritabanı
hangi embedding ile seed edildiyse testler de onunla çalışmalı (compose `fastembed` kullanır).

### LLM
`OPENAI_API_KEY` varsa gpt-4o-mini; yoksa `OLLAMA_URL` ile yerel model; ikisi de yoksa ajanlar
kural tabanlı yollarla çalışır (KB makalesi adımları, şablon SQL).

## Canlıya alma

Sistem tek makinede `docker compose` ile çalışır; dışarıya [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
ile açılır (port açmak, sabit IP veya sertifika gerekmez). Link, makine açık ve container'lar ile
`cloudflared` çalıştığı sürece erişilebilir. Public erişimden önce `.env` içindeki
`AUTH_SECRET`, `CHAINLIT_AUTH_SECRET` ve `DEMO_ACCOUNTS` şifrelerini değiştirin.

**1. Geçici link (hesap ve domain gerekmez):**
```bash
docker compose up -d
cloudflared tunnel --url http://localhost:8080   # https://<rastgele>.trycloudflare.com
```
Adres `cloudflared` her başladığında değişir; deneme ve kısa demolar için.

**2. Sabit link (Cloudflare'e bağlı bir domain gerekir):**
```bash
cloudflared tunnel login
cloudflared tunnel create helpdesk
cloudflared tunnel route dns helpdesk demo.<domain>
cloudflared tunnel run --url http://localhost:8080 helpdesk
```
Kendiliğinden ayağa kalkması için: compose servisleri `restart: unless-stopped` ile tanımlı
(Docker açılınca geri gelir); Docker Desktop'ta *Start when you sign in* açık olsun;
`cloudflared service install <token>` tüneli işletim sistemi servisi olarak kurar (token:
Cloudflare Zero Trust → Networks → Tunnels).

**3. Sunucu / Kubernetes:** herhangi bir Linux VM'de (ör. arm64) aynı compose + named tunnel
yeterli. k3s için manifest'ler `deploy/k8s/` altında: secret'lar
([şablon](deploy/k8s/secrets.example.yaml)) ve `deploy/k8s/ingress.yaml` host'u ayarlanır,
GitHub'a `KUBECONFIG_B64` secret'ı eklenir, Actions → **Deploy** → *Run workflow* arm64 imajları
GHCR'a basar, `kubectl apply -k deploy/` ve migrate job'ını çalıştırır. Bu yol gerçek bir
kümede henüz denenmedi.

## Klasörler
```
services/agent-api   FastAPI + LangGraph (graph/, guardrails/, memory/, core/)
services/mcp-tools   FastMCP server + tools (kb, tickets, sql, users, status)
services/nlu-service /nlu (ONNX Runtime) + kural tabanlı yedek
services/ui          Chainlit
ml/                  veri üretimi, Label Studio, eğitim, ONNX export, değerlendirme, model kartı
db/                  alembic migration'ları, seed (kullanıcı, 500 ticket, 64 KB dokümanı)
evals/               120 senaryo, run_eval.py, raporlar
deploy/              k3s manifest'leri (kustomize), Prometheus/Grafana yapılandırması
docs/                mimari, ADR'ler, eval raporu
```

## Lisans
[MIT](LICENSE) © 2026 Beyza Nur Ulu
