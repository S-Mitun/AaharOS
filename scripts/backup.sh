#!/bin/sh
# MP17: back up the AaharOS database, and prove the backup restores.
#   scripts/backup.sh            -> backups/aaharos-<UTC time>.dump (pg_dump custom format, from the compose `db`)
#   scripts/backup.sh --verify   -> also restores it into a scratch database and compares row counts of the books
# Backups hold DEMO data only on a demo server; on a real one they hold business data: keep them private
# (backups/ is git-ignored).
set -eu
cd "$(dirname "$0")/.."
USER_NAME="${POSTGRES_USER:-aahar}"
DB_NAME="${POSTGRES_DB:-aaharos}"
mkdir -p backups
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
FILE="backups/aaharos-$STAMP.dump"
docker compose exec -T db pg_dump -U "$USER_NAME" -d "$DB_NAME" -Fc > "$FILE"
echo "backup: $FILE ($(wc -c < "$FILE") bytes)"

if [ "${1:-}" = "--verify" ]; then
  CHECK=aaharos_restore_check
  docker compose exec -T db psql -U "$USER_NAME" -d postgres -q -c "DROP DATABASE IF EXISTS $CHECK" -c "CREATE DATABASE $CHECK"
  docker compose exec -T db pg_restore -U "$USER_NAME" -d "$CHECK" --no-owner < "$FILE"
  COUNTS="SELECT string_agg(t || '=' || n, ' ' ORDER BY t) FROM (
    SELECT 'stock_journals' t, count(*) n FROM stock_journals UNION ALL
    SELECT 'stock_lines', count(*) FROM stock_lines UNION ALL
    SELECT 'invoices', count(*) FROM invoices UNION ALL
    SELECT 'payments', count(*) FROM payments UNION ALL
    SELECT 'audit_log', count(*) FROM audit_log UNION ALL
    SELECT 'organizations', count(*) FROM organizations) x"
  SRC=$(docker compose exec -T db psql -U "$USER_NAME" -d "$DB_NAME" -At -c "$COUNTS")
  DST=$(docker compose exec -T db psql -U "$USER_NAME" -d "$CHECK" -At -c "$COUNTS")
  docker compose exec -T db psql -U "$USER_NAME" -d postgres -q -c "DROP DATABASE $CHECK"
  echo "source:   $SRC"
  echo "restored: $DST"
  if [ "$SRC" != "$DST" ]; then echo "restore check FAILED"; exit 1; fi
  echo "restore check OK"
fi
