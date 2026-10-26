import os

from alembic import context
from sqlalchemy import create_engine


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/helpdesk")
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def run_migrations_online() -> None:
    engine = create_engine(database_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
