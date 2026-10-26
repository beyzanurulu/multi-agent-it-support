"""Seed the database with synthetic data: departments, users, 500 tickets, KB.

All names, e-mails and tickets are generated; no real person or company data.

    DATABASE_URL=... python db/seed/seed.py [--reset]
"""

import argparse
import os
import random
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "mcp-tools"))

from mcp_tools.embeddings import get_embedder

SEED_DIR = Path(__file__).parent
FIRST = ["Ayşe", "Mehmet", "Zeynep", "Ahmet", "Elif", "Mustafa", "Fatma", "Emre", "Selin",
         "Burak", "Deniz", "Can", "Ece", "Kerem", "Merve", "Onur", "Gizem", "Hakan", "Nur", "Tolga"]
LAST = ["Yılmaz", "Kaya", "Demir", "Şahin", "Çelik", "Yıldız", "Aydın", "Öztürk", "Arslan",
        "Doğan", "Kılıç", "Aslan", "Koç", "Kurt", "Özdemir"]

# intent -> (category, team, typical severities, sample titles)
INTENTS = {
    "password_reset": ("account", "Service Desk L1", ["low", "medium"],
                       ["Şifre sıfırlama", "Şifremi unuttum", "Parola süresi doldu"]),
    "account_locked": ("account", "Service Desk L1", ["medium", "high"],
                       ["Hesap kilitlendi", "Giriş yapamıyorum"]),
    "vpn_issue": ("vpn", "Network Team", ["medium", "high"],
                  ["VPN bağlanmıyor", "VPN hata 809", "VPN çok yavaş"]),
    "email_issue": ("email", "Messaging Team", ["medium", "high"],
                    ["Outlook açılmıyor", "0x800CCC0E hatası", "Posta kutusu dolu"]),
    "software_install": ("software", "Desktop Support", ["low"],
                         ["Office kurulumu", "Adobe lisans talebi", "Java kurulumu"]),
    "hardware_issue": ("hardware", "Desktop Support", ["medium", "high"],
                       ["Laptop açılmıyor", "Monitör görüntü vermiyor", "Klavye arızası"]),
    "network_issue": ("network", "Network Team", ["medium", "high", "critical"],
                      ["İnternet yok", "Wi-Fi kopuyor", "DNS sorunu"]),
    "access_request": ("access", "IAM Team", ["low"],
                       ["Klasör yetkisi", "ERP erişimi", "Paylaşılan posta kutusu erişimi"]),
    "printer_issue": ("printer", "Desktop Support", ["low", "medium"],
                      ["Yazıcı kağıt sıkıştırıyor", "Yazıcı çevrimdışı", "0x0000011b hatası"]),
}
STATUSES = ["open", "in_progress", "escalated", "resolved", "resolved", "closed", "closed"]
SERVICES = {"vpn": "operational", "email": "operational", "wifi": "operational",
            "sso": "operational", "fileserver": "degraded", "erp": "operational",
            "printserver": "operational"}
DEMO_USERS = [
    ("calisan", "Demo Çalışan", "Muhasebe", "employee"),
    ("uzman", "Demo IT Uzmanı", "Operasyon", "it_specialist"),
    ("yonetici", "Demo Yönetici", "Muhasebe", "manager"),
]


def slug(text: str) -> str:
    table = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return re.sub(r"[^a-z.]", "", text.translate(table).lower().replace(" ", "."))


def parse_kb(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    meta = {"category": "general", "error_codes": ""}
    if match := re.match(r"---\n(.*?)\n---\n", text, re.DOTALL):
        for line in match.group(1).splitlines():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
        text = text[match.end():]
    title = re.search(r"^# (.+)$", text, re.MULTILINE).group(1).strip()
    codes = [c.strip().upper() for c in meta["error_codes"].split(",") if c.strip()]
    return {"id": path.stem, "title": title, "category": meta["category"],
            "error_codes": codes, "content": text.strip()}


def chunk(doc: dict) -> list[str]:
    """One chunk per document section, each prefixed with the title for context."""
    body = doc["content"].split("\n", 1)[1]
    # The shared "when to open a ticket" footer is boilerplate and only adds retrieval noise.
    sections = [s.strip() for s in re.split(r"\n(?=## )", body)
                if s.strip() and not s.strip().startswith("## Ne Zaman Talep")]
    codes = " ".join(doc["error_codes"])
    return [f"{doc['title']} {codes}\n{s}".strip() for s in sections]


def seed_kb(conn: psycopg.Connection) -> int:
    docs = [parse_kb(p) for p in sorted((SEED_DIR / "kb").glob("*.md"))]
    embedder = get_embedder()
    with conn.cursor() as cur:
        for doc in docs:
            cur.execute(
                "INSERT INTO kb_documents (id, title, category, error_codes, content) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title,"
                " category = EXCLUDED.category, error_codes = EXCLUDED.error_codes,"
                " content = EXCLUDED.content",
                (doc["id"], doc["title"], doc["category"], doc["error_codes"], doc["content"]),
            )
            cur.execute("DELETE FROM kb_chunks WHERE doc_id = %s", (doc["id"],))
            chunks = chunk(doc)
            for i, (text, vec) in enumerate(zip(chunks, embedder.embed(chunks))):
                cur.execute(
                    "INSERT INTO kb_chunks (doc_id, chunk_index, content, embedding) "
                    "VALUES (%s, %s, %s, %s::vector)",
                    (doc["id"], i, text, str(vec)),
                )
    return len(docs)


def seed(conn: psycopg.Connection, n_tickets: int = 500, rng_seed: int = 42) -> None:
    rng = random.Random(rng_seed)
    departments = [d.strip() for d in (SEED_DIR / "departments.txt").read_text(
        encoding="utf-8").splitlines() if d.strip()]
    now = datetime.now(UTC)
    with conn.cursor() as cur:
        dep_ids = {}
        for name in departments:
            cur.execute("INSERT INTO departments (name) VALUES (%s) ON CONFLICT (name) DO UPDATE "
                        "SET name = EXCLUDED.name RETURNING id", (name,))
            dep_ids[name] = cur.fetchone()[0]

        users = []
        for uid, name, dep, role in DEMO_USERS:
            users.append((uid, name, f"{uid}@example.local", dep_ids[dep], role, False))
        for i in range(1, 41):
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            role = "it_specialist" if i % 10 == 0 else "manager" if i % 13 == 0 else "employee"
            users.append((f"u{i:03d}", name, f"{slug(name)}{i}@example.local",
                          dep_ids[rng.choice(departments)], role, i % 7 == 0))
        cur.executemany(
            "INSERT INTO users (id, full_name, email, department_id, role, vip) "
            "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING", users)

        for service, status in SERVICES.items():
            cur.execute("INSERT INTO system_status (service, status) VALUES (%s, %s) "
                        "ON CONFLICT (service) DO UPDATE SET status = EXCLUDED.status",
                        (service, status))

        employee_ids = [u[0] for u in users if u[4] == "employee"]
        for _ in range(n_tickets):
            intent = rng.choice(list(INTENTS))
            category, team, severities, titles = INTENTS[intent]
            title = rng.choice(titles)
            created = now - timedelta(days=rng.uniform(0, 90))
            status = rng.choice(STATUSES)
            resolved = (created + timedelta(hours=rng.uniform(1, 72))
                        if status in ("resolved", "closed") else None)
            cur.execute(
                "INSERT INTO tickets (ticket_no, user_id, title, description, intent, category,"
                " severity, status, assigned_team, created_at, updated_at, resolved_at) "
                "VALUES ('INC-' || nextval('ticket_no_seq'), %s, %s, %s, %s, %s, %s, %s, %s, %s,"
                " %s, %s) RETURNING id",
                (rng.choice(employee_ids), title, f"{title} (sentetik kayıt)", intent, category,
                 rng.choice(severities), status, team, created, resolved or created, resolved),
            )
            ticket_id = cur.fetchone()[0]
            cur.execute("INSERT INTO ticket_events (ticket_id, event, detail, actor, created_at) "
                        "VALUES (%s, 'created', %s, 'seed', %s)",
                        (ticket_id, Jsonb({"status": "open"}), created))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="truncate data tables first")
    parser.add_argument("--tickets", type=int, default=500)
    args = parser.parse_args()
    url = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/helpdesk")
    with psycopg.connect(url) as conn:
        if args.reset:
            conn.execute("TRUNCATE ticket_events, tickets, notifications, audit_log, "
                         "usage_counters, users, departments RESTART IDENTITY CASCADE")
            conn.execute("ALTER SEQUENCE ticket_no_seq RESTART WITH 10001")
        already = conn.execute("SELECT count(*) FROM tickets").fetchone()[0]
        if already == 0:
            seed(conn, n_tickets=args.tickets)
        docs = seed_kb(conn)
        conn.commit()
        total = conn.execute("SELECT count(*) FROM tickets").fetchone()[0]
        print(f"seeded: tickets={total}, kb_documents={docs}")


if __name__ == "__main__":
    main()
