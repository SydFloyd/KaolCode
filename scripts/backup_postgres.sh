#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/opt/codex-home/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
TARGET="${BACKUP_ROOT}/codex_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_ROOT}"

docker compose exec -T postgres pg_dump -U codex -d codex | gzip > "${TARGET}"

find "${BACKUP_ROOT}" -type f -name "codex_*.sql.gz" -mtime +"${RETENTION_DAYS}" -delete
echo "Backup written to ${TARGET}"
