#!/usr/bin/env bash
# All services in one container for the Hugging Face Space: Postgres, migrations + seed,
# mcp-tools, nlu-service, agent-api in the background, Chainlit on $PORT (7860).
# The data is synthetic and re-seeded on every start.
set -euo pipefail
cd "$(dirname "$0")/../.."

export PGDATA=/tmp/pgdata
PG=${PG_BIN:-/usr/lib/postgresql/16/bin}
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  # trust: Postgres only listens on 127.0.0.1 inside the container
  "$PG/initdb" -D "$PGDATA" -U postgres --auth=trust >/dev/null
fi
"$PG/pg_ctl" -D "$PGDATA" -o "-c listen_addresses=127.0.0.1 -k /tmp" -l /tmp/postgres.log -w start
"$PG/psql" -h 127.0.0.1 -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='helpdesk'" \
  | grep -q 1 || "$PG/createdb" -h 127.0.0.1 -U postgres helpdesk

alembic -c db/alembic.ini upgrade head
python db/seed/seed.py

PYTHONPATH=services/mcp-tools PORT=8001 python -m mcp_tools.server &
PYTHONPATH=services/nlu-service uvicorn nlu_service.main:app --host 127.0.0.1 --port 8002 &
PYTHONPATH=services/agent-api uvicorn agent_api.main:app --host 127.0.0.1 --port 8000 &

for _ in $(seq 60); do
  curl -fs http://127.0.0.1:8000/health >/dev/null && break
  sleep 1
done

# Chainlit turns on its own SQL data layer when it sees DATABASE_URL; the UI keeps no data.
(cd services/ui && env -u DATABASE_URL -u READONLY_DATABASE_URL \
  chainlit run chainlit_app.py --headless --host 0.0.0.0 --port "${PORT:-7860}") &

# If any service dies, exit so the Space restarts the container.
wait -n
exit 1
