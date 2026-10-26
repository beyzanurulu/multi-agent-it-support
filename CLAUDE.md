# CLAUDE.md

Türkçe IT destek multi-agent platformu. Önce oku:
- `project2-multi-agent-plan.md` — plan, kısıtlar, hedef metrikler (kapsam dışına çıkma)
- `README.md` — durum tablosu (✅ / ⏳), çalıştırma
- `docs/architecture.md` — servisler, mesaj akışı, güvenlik katmanları
- İlgili işe göre: `docs/adr/`, `docs/eval-report.md`, `ml/MODEL_CARD.md`

## Yapı
- `services/agent-api/agent_api` — FastAPI + LangGraph. `graph/` (supervisor, planner, triage,
  solution, ticket, analytics, build), `guardrails/`, `memory/`, `core/`, `runner.py`, `main.py`
- `services/mcp-tools/mcp_tools` — FastMCP server (8 tool), Postgres/pgvector
- `services/nlu-service/nlu_service` — `/nlu`; `models/nlu/model.onnx` yoksa `rules.py`
- `services/ui/chainlit_app.py` — Chainlit
- `ml/` eğitim hattı · `db/` alembic + seed · `evals/` 120 senaryo · `deploy/` k3s + izleme
- Tek `pyproject.toml`; servisler extra ile kurulur: `agent`, `mcp`, `nlu`, `ui`, `db`, `ml`

## Komutlar
```bash
uv sync --extra agent --extra mcp --extra nlu --extra db --extra ui
docker compose up -d postgres
uv run alembic -c db/alembic.ini upgrade head && uv run python db/seed/seed.py
uv run ruff check .
uv run pytest -q services ml
uv run python evals/run_eval.py --check      # CI kapısı; rapor evals/reports/
docker compose up --build                    # tüm sistem, UI :8080 (calisan/uzman/yonetici, şifre demo)
```
Test/eval ortamı (`.env`):
```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/helpdesk
READONLY_DATABASE_URL=postgresql://helpdesk_readonly:readonly@localhost:5432/helpdesk
EMBEDDING_PROVIDER=hashing
```
agent-api testleri `NLU_URL=inprocess`, `MCP_URL=inprocess` ile çalışır (conftest ayarlar).

## Kurallar
- Kısıtlar plandaki tabloda: maliyet (ucuz LLM, günlük bütçe), arm64 imajlar, yeni ajan/özellik
  yok — önce eval skorları, tek repo.
- Veri her zaman sentetik; gerçek kişi/şirket verisi ekleme.
- README'ye veya rapora yalnızca repoda kodla/raporla doğrulanabilen sayı yaz. Ölçülmemiş metrik
  "⏳" kalır.
- Yazma tool'ları (`create_ticket`, `escalate_ticket`) yalnızca `interrupt()` onayından sonra.
- Analytics SQL'i her zaman `guardrails/sql_guard.py`'den geçer; yeni tablo açılacaksa hem
  `ALLOWED_TABLES` hem read-only rol grant'ı güncellenir (yeni alembic migration).
- Yeni tool → `mcp_tools/server.py` TOOLS + `guardrails/limits.py` ajan/rol allowlist + test.
- NLU etiketleri `nlu_service/labels.py`'de; değişirse ml/ ve planner/triage tabloları da güncellenir.
- Davranış değişikliğinden sonra eval'i çalıştır; skor düşerse sebebini bul, iyileştirme
  yaptıysan `docs/eval-report.md`'ye önce/sonra satırı ekle.
- LLM opsiyonel: anahtar yokken her ajan kural tabanlı yolla çalışmaya devam etmeli.

## Açık işler
- BERTurk eğitimi: 600 örnek Label Studio'da doğrulanacak, Colab/Kaggle GPU'da eğitilecek,
  `ml/MODEL_CARD.md` metrikleri doldurulacak.
- LLM açıkken eval (LLM-as-judge, tutarlılık, latency, maliyet) ve rapor güncellemesi.
- Docker imajları ve k8s manifest'leri henüz gerçek ortamda denenmedi.
- Canlıya alma: Oracle VM + k3s + Cloudflare + `KUBECONFIG_B64` secret'ı.
