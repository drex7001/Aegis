#!/usr/bin/env bash
# Aegis backup (speckit T15): pg_dump the claim store + mirror the MinIO evidence
# vault into a single timestamped directory. Idempotent per timestamp.
#
#   bash scripts/backup.sh [DEST_DIR]
#
# DEST_DIR defaults to backups/<UTC-timestamp>. The Postgres dump is a custom-
# format archive (pg_restore-ready); the vault buckets are mirrored verbatim.
# Encrypt the resulting directory at rest (age/gpg) — it holds real names from
# public reporting (spec 03 §7). See docs/BACKUP_RESTORE.md for the runbook.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a || true
ENVFILE_ARGS=(); [ -f "$ROOT/.env" ] && ENVFILE_ARGS=(--env-file "$ROOT/.env")
COMPOSE=(docker compose "${ENVFILE_ARGS[@]}" -f "$ROOT/infra/docker-compose.yml")

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${1:-$ROOT/backups/$STAMP}"
mkdir -p "$DEST"

PGUSER="${POSTGRES_USER:-aegis}"
PGDB="${POSTGRES_DB:-aegis}"
MC_USER="${MINIO_ROOT_USER:-aegis}"
MC_PASS="${MINIO_ROOT_PASSWORD:-aegis-minio-dev}"
NET="${COMPOSE_PROJECT_NAME:-aegis}_default"

# Docker-friendly absolute path (Windows Git Bash needs the C:/… form).
hostpath() { if pwd -W >/dev/null 2>&1; then (cd "$1" && pwd -W); else (cd "$1" && pwd); fi; }

step() { printf '\n==> %s\n' "$*"; }

step "postgres: pg_dump ($PGDB) → db.dump (custom format)"
"${COMPOSE[@]}" exec -T postgres pg_dump -U "$PGUSER" -d "$PGDB" -Fc > "$DEST/db.dump"
echo "wrote $DEST/db.dump ($(wc -c < "$DEST/db.dump") bytes)"

step "minio: mirror raw-landing + evidence + exports buckets → vault/"
mkdir -p "$DEST/vault"
MSYS_NO_PATHCONV=1 docker run --rm --network "$NET" --entrypoint /bin/sh \
  -v "$(hostpath "$DEST/vault"):/backup" minio/mc -c "
    mc alias set l http://minio:9000 '$MC_USER' '$MC_PASS' >/dev/null
    for bucket in raw-landing evidence exports; do
      mc mirror --overwrite --quiet \"l/\$bucket\" \"/backup/\$bucket\" 2>/dev/null || echo \"  (bucket \$bucket empty)\"
    done
    echo 'vault mirror complete'
  "

step "manifest"
cat > "$DEST/manifest.json" <<EOF
{
  "created_at": "$STAMP",
  "postgres_db": "$PGDB",
  "db_dump": "db.dump",
  "vault_dir": "vault",
  "buckets": ["raw-landing", "evidence", "exports"],
  "tool": "scripts/backup.sh"
}
EOF
echo "wrote $DEST/manifest.json"

step "backup complete: $DEST"
