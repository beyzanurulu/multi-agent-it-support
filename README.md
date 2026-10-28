# Türkçe IT Destek Multi-Agent Platformu

Şirket çalışanının Türkçe yazdığı IT sorununu anlayan (intent + NER), planlayan, bilgi
tabanından çözen, gerekirse onay alarak ticket açan ve yöneticiye ticket istatistiklerini SQL
ile raporlayan multi-agent sistem. 

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
| **Public URL** | ⏳ sunucu bekleniyor | [Canlıya alma](#canlıya-alma) |

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

**Kalıcı ücretsiz link — Hugging Face Space (kart gerekmez):** New Space → SDK **Gradio** →
CPU basic; [deploy/hf-space/](deploy/hf-space/) içindeki `app.py`, `requirements.txt`,
`packages.txt` ve `README.md` dosyalarını Space'e yükleyin. Arayüz yine Chainlit'tir; `app.py`
kodu GitHub'dan çeker, bağımlılıkları kurar ve tüm servisleri tek container'da başlatır (ilk açılış
~7 dk). Repo public olmalı. 48 saat ziyaret almayan Space uyur, veriler her başlangıçta sıfırlanır.

**En hızlısı — geçici public link (ücretsiz, domain gerekmez):** sistemi yerelde çalıştırıp
[Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/)
ile açın. Bilgisayar açık kaldığı sürece `https://<rastgele>.trycloudflare.com` adresinden erişilir.
```bash
docker compose up -d
cloudflared tunnel --url http://localhost:8080
```
Public erişimde `.env` içindeki `AUTH_SECRET`, `CHAINLIT_AUTH_SECRET` ve `DEMO_ACCOUNTS`
şifrelerini değiştirin.

**Kalıcı, tek sunucu:** herhangi bir Linux VM'de (ör. Hetzner CAX11 arm64) aynı
`docker compose up -d` + `cloudflared` (named tunnel) yeterli; Kubernetes gerekmez.

**k3s (Oracle Cloud Always Free Ampere VM + Cloudflare):**
1. VM'e k3s: `curl -sfL https://get.k3s.io | sh -s - --tls-san <PUBLIC_IP>`.
2. `kubectl -n helpdesk create secret generic helpdesk-secrets --from-env-file=.env.prod`
   ([şablon](deploy/k8s/secrets.example.yaml)); Cloudflare Origin sertifikası →
   `cloudflare-origin` TLS secret'ı; `deploy/k8s/ingress.yaml` içindeki host'u güncelle.
3. GitHub → Settings → Secrets: `KUBECONFIG_B64`. GHCR paketleri private ise küme için
   image pull secret gerekir.
4. Actions → **Deploy** → *Run workflow* (sunucu hazır olana kadar deploy otomatik tetiklenmez):
   arm64 imajlar GHCR'a → `kubectl apply -k deploy/` → migrate job.

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
