import os

os.environ.setdefault("EMBEDDING_PROVIDER", "hashing")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/helpdesk")
os.environ.setdefault(
    "READONLY_DATABASE_URL", "postgresql://helpdesk_readonly:readonly@localhost:5432/helpdesk"
)
