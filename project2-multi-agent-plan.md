# Proje 2 — Multi-Agent Orchestration Framework
> Başlangıç: Kasım 2026 | Hedef tamamlanma: Aralık 2026 sonu

---

## Amaç
Kurumsal bir domain'de çalışan, birden fazla ajanın koordineli hareket ettiği,
üretim ortamına alınabilir bir multi-agent sistemi. Doggo'nun mimarisini baz al
ama domain'i kurumsal yap — **IT destek otomasyonu** (teknik destek talebi gelen,
uygun ajana yönlendiren, çözüm üreten, ticket açan sistem).

Bu domain hem gerçekçi hem de ilandaki "kurumsal AI kullanım senaryoları" maddesini
doğrudan karşılar.

---

## Domain Seçimi: IT Destek Otomasyonu

Neden bu domain:
- Gerçek kurumsal use case, portfolio'da inandırıcı
- Doggo'dan mimari transfer edilebilir, sıfırdan başlamak gerekmez
- NLP (intent classification) + RAG (bilgi tabanı) + tool calling doğal olarak giriyor
- Architecht'in hedef müşterileri kurumsal şirketler — tam isabet

---

## Tech Stack

| Katman | Teknoloji | Neden |
|---|---|---|
| **Orchestration** | LangGraph (StateGraph) | Stateful workflow, conditional edges |
| **LLM** | OpenAI GPT-4o-mini | Tool calling desteği güçlü |
| **Tracing** | LangSmith | Production observability |
| **API** | FastAPI + WebSocket | Real-time agent stream |
| **Tool Framework** | FastMCP | İlandaki spesifik gereksinim |
| **Intent Classification** | Fine-tuned model veya few-shot LLM | NER/Intent ilanında geçiyor |
| **Vector DB** | ChromaDB (bilgi tabanı) | Lokal, sıfır maliyet |
| **Memory** | LangGraph checkpointer (SQLite) | Conversation memory |
| **Validation** | Guardrails AI + Pydantic | Output doğrulama |
| **Container** | Docker + Docker Compose | Deploy |
| **CI/CD** | GitHub Actions | Otomatik test |
| **Monitoring** | LangSmith + structlog | Trace ve log |

---

## Ajan Mimarisi

```
┌─────────────────────────────────────────────────────────┐
│                    Kullanıcı / Sistem                    │
└──────────────────────────┬──────────────────────────────┘
                           │ WebSocket / REST
┌──────────────────────────▼──────────────────────────────┐
│               FastAPI Gateway                           │
│          Auth │ Session Yönetimi │ Rate Limit           │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│              SUPERVISOR AGENT                           │
│   • Intent classification (ne tür sorun?)               │
│   • Ajan seçimi ve yönlendirme                         │
│   • Conversation state yönetimi                         │
│   • Human-in-the-loop trigger                          │
└────────┬──────────────────┬──────────────────┬──────────┘
         │                  │                  │
┌────────▼───────┐ ┌────────▼───────┐ ┌────────▼───────┐
│  TRIAGE AGENT  │ │ SOLUTION AGENT │ │  TICKET AGENT  │
│                │ │                │ │                │
│ • Sorun        │ │ • Bilgi tabanı │ │ • Ticket açma  │
│   sınıflandır  │ │   RAG search   │ │ • Öncelik      │
│ • Aciliyet     │ │ • Çözüm öner   │ │   belirleme    │
│   belirle      │ │ • Adım adım    │ │ • Atama        │
│ • Metadata     │ │   rehberlik    │ │ • Bildirim     │
│   topla        │ │ • Doğrula      │ │   gönder       │
└────────┬───────┘ └────────┬───────┘ └────────┬───────┘
         │                  │                  │
┌────────▼──────────────────▼──────────────────▼───────┐
│                    TOOL LAYER (FastMCP)               │
│  search_kb │ create_ticket │ send_notification │      │
│  check_system_status │ escalate │ get_user_info │     │
└──────────────────────────────────────────────────────┘
         │                  │
┌────────▼───────┐ ┌────────▼───────┐
│  ChromaDB      │ │  Mock CRM API  │
│  (KB Vector)   │ │  (ticket sys)  │
└────────────────┘ └────────────────┘
```

---

## LangGraph State Tasarımı

```python
class AgentState(TypedDict):
    # Conversation
    messages: Annotated[list, add_messages]
    user_id: str
    session_id: str
    
    # Triage
    intent: str               # "password_reset", "software_install", "network"...
    severity: str             # "low", "medium", "high", "critical"
    category: str
    
    # Solution
    kb_results: list[dict]
    proposed_solution: str
    solution_accepted: bool
    
    # Ticket
    ticket_id: Optional[str]
    ticket_status: str
    escalated: bool
    
    # Control
    current_agent: str
    iteration_count: int      # loop koruma
    human_requested: bool
```

---

## Kapsam

### ✅ Dahil
- Supervisor + 3 specialized agent (Triage, Solution, Ticket)
- LangGraph StateGraph ile conditional routing
- FastMCP ile tool server (5+ tool)
- Conversation memory (SQLite checkpointer)
- Intent classification (few-shot prompting + keyword fallback)
- ChromaDB'ye yüklü mock IT bilgi tabanı (50+ doküman)
- Human-in-the-loop: kritik işlemlerde onay bekleme
- Guardrails: output validation, infinite loop koruması
- LangSmith tracing (her agent step izlenebilir)
- WebSocket ile real-time streaming
- Docker Compose deploy

### ❌ Kapsam Dışı
- Gerçek CRM entegrasyonu (mock API yeterli)
- Frontend (Gradio minimal demo)
- Fine-tuned intent classifier (few-shot yeterli — sonradan eklenebilir)
- Multi-tenant yapı
- Gerçek bildirim sistemi (e-posta/SMS)

---

## FastMCP Tool Listesi

```python
# tools/it_tools.py

@mcp.tool()
async def search_knowledge_base(query: str, category: str = None) -> list[dict]:
    """IT bilgi tabanında çözüm ara"""

@mcp.tool()
async def create_ticket(
    user_id: str, 
    title: str, 
    description: str, 
    severity: str,
    category: str
) -> dict:
    """Yeni destek talebi oluştur"""

@mcp.tool()
async def check_system_status(service_name: str) -> dict:
    """Servis durumunu kontrol et"""

@mcp.tool()
async def get_user_info(user_id: str) -> dict:
    """Kullanıcı profili ve geçmiş talepleri getir"""

@mcp.tool()
async def escalate_ticket(ticket_id: str, reason: str) -> dict:
    """Talebi üst seviyeye ilet"""

@mcp.tool()
async def send_notification(user_id: str, message: str, channel: str) -> bool:
    """Kullanıcıya bildirim gönder (mock)"""
```

---

## Klasör Yapısı

```
multi-agent-it-support/
├── src/
│   ├── api/
│   │   ├── main.py              # FastAPI app
│   │   ├── routes/
│   │   │   ├── chat.py          # WebSocket + REST endpoint
│   │   │   └── admin.py         # Trace görüntüleme
│   │   └── deps.py
│   ├── agents/
│   │   ├── graph.py             # LangGraph StateGraph tanımı
│   │   ├── state.py             # AgentState TypedDict
│   │   ├── supervisor.py        # Routing logic
│   │   ├── triage.py            # Triage agent node
│   │   ├── solution.py          # Solution agent node
│   │   ├── ticket.py            # Ticket agent node
│   │   └── human_loop.py        # Human-in-the-loop handler
│   ├── tools/
│   │   ├── server.py            # FastMCP server
│   │   └── it_tools.py          # Tool implementasyonları
│   ├── memory/
│   │   ├── checkpointer.py      # SQLite checkpointer
│   │   └── kb_loader.py         # ChromaDB bilgi tabanı yükleme
│   ├── guardrails/
│   │   ├── output_validator.py  # Guardrails AI entegrasyonu
│   │   └── loop_guard.py        # Iteration limiti
│   └── core/
│       ├── config.py
│       └── langsmith.py         # Tracing setup
├── data/
│   └── knowledge_base/          # Mock IT dokümanları (markdown)
│       ├── password_reset.md
│       ├── vpn_setup.md
│       ├── software_install.md
│       └── ...
├── tests/
│   ├── test_graph.py            # Agent flow testleri
│   ├── test_tools.py
│   └── test_guardrails.py
├── .github/workflows/
│   └── ci.yml
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```

---

## Adım Adım Geliştirme Planı

### Hafta 1 — Temel Ajan İskeleti (Gün 1–7)
- [ ] Repo init, uv env, pyproject.toml
- [ ] AgentState TypedDict tasarımı
- [ ] Supervisor node — basit routing (intent keyword bazlı)
- [ ] Triage agent node — metadata toplama
- [ ] LangGraph StateGraph — 3 node, conditional edges
- [ ] LangSmith tracing kurulumu

### Hafta 2 — Tool Layer (Gün 8–14)
- [ ] FastMCP server setup
- [ ] 6 tool implementasyonu (mock data ile)
- [ ] ChromaDB — 50 doküman yükle, search tool çalıştır
- [ ] Solution agent — RAG + tool calling entegrasyonu
- [ ] Ticket agent — create/escalate flow

### Hafta 3 — Güvenlik ve Sağlamlık (Gün 15–21)
- [ ] Human-in-the-loop — kritik işlemlerde interrupt
- [ ] Guardrails AI — output şema doğrulama
- [ ] Loop guard — max iteration koruması
- [ ] SQLite checkpointer — konuşma memory
- [ ] Intent classification iyileştirme (few-shot)

### Hafta 4 — Deploy ve Demo (Gün 22–30)
- [ ] FastAPI WebSocket endpoint
- [ ] Gradio demo UI (chat arayüzü)
- [ ] Dockerfile + Docker Compose
- [ ] GitHub Actions CI
- [ ] README — mimari diyagram, demo video linki
- [ ] LangSmith trace ekran görüntüleri (her agent step görünür)

---

## Kısıtlar

| Kısıt | Detay |
|---|---|
| **Maliyet** | GPT-4o-mini kullan; LangSmith free tier yeterli |
| **Zaman** | ~30 gün; scope genişletme yok |
| **Tek geliştirici** | Monorepo, ayrı servis yok |
| **Veri** | Gerçek kullanıcı verisi yok; mock/sentetik |
| **Karmaşıklık** | 3 agent yeterli; 5+ agent scope creep |

---

## Başarı Kriterleri
- Supervisor doğru ajanı seçiyor: %90+ test case'de
- Infinite loop yok: max 10 iterasyon sonra graceful çıkış
- LangSmith'te her agent adımı görünür, trace eksiksiz
- Human-in-the-loop: kritik işlem öncesi onay akışı çalışıyor
- Docker Compose'da tek komutla ayağa kalkıyor
- 5 farklı IT senaryosu için uçtan uca test geçiyor

---

## Architecht İlanıyla Örtüşme

| İlan Maddesi | Karşılayan Özellik |
|---|---|
| Çoklu ajan mimarileri tasarlanması | StateGraph + Supervisor pattern |
| Ajanlar arası iletişim, shared memory | AgentState + SQLite checkpointer |
| Tool-calling yaklaşımları | FastMCP tool server |
| Otonom ajan davranışlarının test edilmesi | pytest ajan flow testleri |
| Guardrail'lerin uygulanması | Guardrails AI + loop guard |
| Teknik dokümantasyon | README + LangSmith trace görselleri |

---

## Portfolio Çıktısı
- GitHub repo (public) — açıklayıcı README, mimari diyagram
- LangSmith trace ekran görüntüleri (agent step step izlenebilir)
- Demo video — 3 farklı IT senaryosu (şifre sıfırlama, yazılım kurulum, network sorunu)
- Docker Compose ile çalıştırma kılavuzu
