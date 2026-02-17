#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <backup.sql.gz>"
  exit 1
fi

BACKUP_FILE="$1"

if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "Backup file not found: ${BACKUP_FILE}"
  exit 1
fi

gunzip -c "${BACKUP_FILE}" | docker compose exec -T postgres psql -U codex -d codex
echo "Restore complete from ${BACKUP_FILE}"
