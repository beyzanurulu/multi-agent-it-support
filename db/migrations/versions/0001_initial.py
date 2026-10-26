"""Initial schema: users, tickets, audit, KB (pgvector), analytics view, read-only role.

Revision ID: 0001
Revises:
"""

import os

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
    CREATE TABLE departments (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE
    );

    CREATE TABLE users (
        id TEXT PRIMARY KEY,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        department_id INT REFERENCES departments(id),
        role TEXT NOT NULL CHECK (role IN ('employee', 'it_specialist', 'manager')),
        vip BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE tickets (
        id SERIAL PRIMARY KEY,
        ticket_no TEXT NOT NULL UNIQUE,
        user_id TEXT NOT NULL REFERENCES users(id),
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        intent TEXT NOT NULL,
        category TEXT NOT NULL,
        severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
        status TEXT NOT NULL DEFAULT 'open'
            CHECK (status IN ('open', 'in_progress', 'escalated', 'resolved', 'closed')),
        assigned_team TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        resolved_at TIMESTAMPTZ
    );
    CREATE INDEX ix_tickets_user ON tickets(user_id);
    CREATE INDEX ix_tickets_created ON tickets(created_at);
    CREATE SEQUENCE ticket_no_seq START 10001;

    CREATE TABLE ticket_events (
        id SERIAL PRIMARY KEY,
        ticket_id INT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
        event TEXT NOT NULL,
        detail JSONB NOT NULL DEFAULT '{}',
        actor TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE system_status (
        service TEXT PRIMARY KEY,
        status TEXT NOT NULL CHECK (status IN ('operational', 'degraded', 'outage')),
        note TEXT,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE notifications (
        id SERIAL PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id),
        channel TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE audit_log (
        id BIGSERIAL PRIMARY KEY,
        actor TEXT NOT NULL,
        role TEXT,
        action TEXT NOT NULL,
        payload JSONB NOT NULL DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE usage_counters (
        day DATE NOT NULL,
        user_id TEXT NOT NULL,
        messages INT NOT NULL DEFAULT 0,
        tokens INT NOT NULL DEFAULT 0,
        PRIMARY KEY (day, user_id)
    );

    CREATE TABLE kb_documents (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        error_codes TEXT[] NOT NULL DEFAULT '{}',
        content TEXT NOT NULL
    );
    """)
    op.execute(f"""
    CREATE TABLE kb_chunks (
        id SERIAL PRIMARY KEY,
        doc_id TEXT NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
        chunk_index INT NOT NULL,
        content TEXT NOT NULL,
        embedding vector({EMBEDDING_DIM}) NOT NULL,
        tsv tsvector GENERATED ALWAYS AS (to_tsvector('turkish', content)) STORED,
        UNIQUE (doc_id, chunk_index)
    );
    CREATE INDEX ix_kb_chunks_embedding ON kb_chunks USING hnsw (embedding vector_cosine_ops);
    CREATE INDEX ix_kb_chunks_tsv ON kb_chunks USING gin (tsv);
    """)
    # Analytics only ever sees this view: no e-mail addresses or free-text descriptions.
    op.execute("""
    CREATE VIEW v_tickets AS
    SELECT t.ticket_no, t.intent, t.category, t.severity, t.status, t.assigned_team,
           t.created_at, t.resolved_at, d.name AS department, u.role AS user_role
    FROM tickets t
    JOIN users u ON u.id = t.user_id
    LEFT JOIN departments d ON d.id = u.department_id;
    """)
    password = os.environ.get("READONLY_DB_PASSWORD", "readonly").replace("'", "''")
    op.execute(f"""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'helpdesk_readonly') THEN
            CREATE ROLE helpdesk_readonly LOGIN PASSWORD '{password}';
        END IF;
    END $$;
    GRANT USAGE ON SCHEMA public TO helpdesk_readonly;
    GRANT SELECT ON v_tickets, departments TO helpdesk_readonly;
    ALTER ROLE helpdesk_readonly SET default_transaction_read_only = on;
    ALTER ROLE helpdesk_readonly SET statement_timeout = '5s';
    """)


def downgrade() -> None:
    op.execute("""
    DROP VIEW IF EXISTS v_tickets;
    DROP TABLE IF EXISTS kb_chunks, kb_documents, usage_counters, audit_log, notifications,
        system_status, ticket_events, tickets, users, departments CASCADE;
    DROP SEQUENCE IF EXISTS ticket_no_seq;
    """)
