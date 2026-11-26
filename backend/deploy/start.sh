#!/bin/sh
# Hosted demo start-up (see the root Dockerfile and render.yaml):
#  1. apply the migrations (as the database owner, AAHAR_MIGRATION_DATABASE_URL)
#  2. seed the permanent DEMO factory: logins, master data, the MP13 history; idempotent, and it re-activates the DEMO
#     logins and resets their passwords to DEMO_PASSWORD_<ROLE> (default change-me-demo) on every start
#  3. in the background, replay NIT's nine steps on a fresh BENCHMARK tenant so the home page shows the live
#     26-row scoreboard (AAHAR_BENCHMARK_ON_START=0 turns it off; each run adds one small BENCHMARK tenant)
#  4. serve the API and the built web app on $PORT as the row-level-security role (AAHAR_DATABASE_URL)
set -e
cd /srv/backend
# Render sets RENDER_EXTERNAL_URL (https://<service>.onrender.com): the passport QR codes point there.
export AAHAR_PUBLIC_BASE_URL="${AAHAR_PUBLIC_BASE_URL:-${RENDER_EXTERNAL_URL:-http://localhost:8000}}"
alembic upgrade head
python -m app.cli.seed_demo
python -m app.cli.supabase_users  # hosted sign-in: the DEMO logins exist in Supabase Auth
if [ "${AAHAR_BENCHMARK_ON_START:-1}" = "1" ]; then
  (sleep 20 && python /srv/benchmark/runner.py > /tmp/benchmark.log 2>&1) &
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
