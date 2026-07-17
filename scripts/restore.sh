#!/usr/bin/env bash
# Aegis restore (speckit T15): restore a backup directory into a running compose
# stack, then rebuild projections. DESTRUCTIVE — drops and recreates the target
# database. Intended for a CLEAN stack (a fresh `make nuke up`).
#
#   bash scripts/restore.sh BACKUP_DIR
#
# See docs/BACKUP_RESTORE.md for the full drill.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a || true
ENVFILE_ARGS=(); [ -f "$ROOT/.env" ] && ENVFILE_ARGS=(--env-file "$ROOT/.env")
COMPOSE=(docker compose "${ENVFILE_ARGS[@]}" -f "$ROOT/infra/docker-compose.yml")

SRC="${1:?usage: restore.sh BACKUP_DIR}"
[ -f "$SRC/db.dump" ] || { echo "ERROR: $SRC/db.dump not found" >&2; exit 1; }

PGUSER="${POSTGRES_USER:-aegis}"
PGDB="${POSTGRES_DB:-aegis}"
MC_USER="${MINIO_ROOT_USER:-aegis}"
MC_PASS="${MINIO_ROOT_PASSWORD:-aegis-minio-dev}"
NET="${COMPOSE_PROJECT_NAME:-aegis}_default"
PY=""; for c in python3 python; do "$c" -c 'pass' >/dev/null 2>&1 && { PY="$c"; break; }; done

# Docker-friendly absolute path (Windows Git Bash needs the C:/… form).
hostpath() { if pwd -W >/dev/null 2>&1; then (cd "$1" && pwd -W); else (cd "$1" && pwd); fi; }

step() { printf '\n==> %s\n' "$*"; }

step "postgres: drop + recreate database $PGDB"
"${COMPOSE[@]}" exec -T postgres psql -U "$PGUSER" -d postgres -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$PGDB' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS $PGDB;
CREATE DATABASE $PGDB OWNER $PGUSER;
SQL

step "postgres: pg_restore db.dump"
"${COMPOSE[@]}" exec -T postgres pg_restore -U "$PGUSER" -d "$PGDB" --no-owner < "$SRC/db.dump"
echo "database restored"

step "minio: restore vault buckets"
if [ -d "$SRC/vault" ]; then
  MSYS_NO_PATHCONV=1 docker run --rm --network "$NET" --entrypoint /bin/sh \
    -v "$(hostpath "$SRC/vault"):/backup:ro" minio/mc -c "
      mc alias set l http://minio:9000 '$MC_USER' '$MC_PASS' >/dev/null
      for bucket in raw-landing evidence exports; do
        mc mb --ignore-existing \"l/\$bucket\" >/dev/null
        [ -d \"/backup/\$bucket\" ] && mc mirror --overwrite --quiet \"/backup/\$bucket\" \"l/\$bucket\" || true
      done
      echo 'vault restored'
    "
else
  echo "WARN: no vault/ directory in backup — skipping object restore"
fi

step "projections: rebuild from the restored claim store"
AEGIS_DATABASE_URL="${AEGIS_DATABASE_URL:-postgresql+psycopg://$PGUSER:${POSTGRES_PASSWORD:-aegis-dev}@localhost:5433/$PGDB}" \
  "$PY" -m aegis.cli projections rebuild || echo "WARN: projection rebuild failed (run 'aegis projections rebuild' manually)"

step "audit: verify chain integrity after restore"
AEGIS_DATABASE_URL="${AEGIS_DATABASE_URL:-postgresql+psycopg://$PGUSER:${POSTGRES_PASSWORD:-aegis-dev}@localhost:5433/$PGDB}" \
  "$PY" -m aegis.cli audit verify

step "restore complete from $SRC"
