# Codex-at-Home v1

Safety-first local coding-agent platform optimized for externally useful output.

## What this repository includes

- FastAPI orchestrator with required REST endpoints:
  - `POST /api/v1/webhooks/github`
  - `POST /api/v1/jobs`
  - `POST /api/v1/intake/text`
  - `GET /api/v1/jobs/{job_id}`
  - `POST /api/v1/jobs/{job_id}/approve`
  - `POST /api/v1/jobs/{job_id}/reject`
  - `POST /api/v1/control/kill-switch`
  - `POST /api/v1/control/resume`
  - `GET /metrics`
- Worker process using Redis queue (RQ), Postgres-backed state, and GitHub App execution path for real draft PRs.
- Worker exposes Prometheus metrics on `WORKER_METRICS_PORT` (default `9108`) for failure/cost telemetry.
- Policy engine enforcing repo allowlist, blocked commands, path restrictions, caps, and approvals.
- Structured artifacts per job under `data/artifacts/{job_id}`.
- Observability stack: Prometheus, Loki, Grafana, Alertmanager.
- Bootstrap scripts and Linux systemd unit templates.

## Quick start (desktop-first)

1. Copy environment file and fill secrets:
   ```bash
   cp .env.example .env
   ```
   Set `RUN_MODE=fast` for local-safe operation or `RUN_MODE=release` for live GitHub issue/PR flow.
2. Start stack:
   ```bash
   docker compose up -d --build
   ```
3. Verify health:
   - Orchestrator: `http://localhost:8080/healthz`
   - Metrics: `http://localhost:8080/metrics`
   - Grafana: `http://localhost:3000` (`admin/admin`, change immediately)
4. Run tests:
   ```bash
   python -m pip install -e ".[dev]"
   pytest
   ```

## Default safety behavior

- New jobs from `agent-ready` GitHub issue labels, `/api/v1/intake/text`, or explicit manual API.
- `RUN_MODE=fast`: no GitHub writes, synthetic local issue ids, no PR creation.
- `RUN_MODE=release`: real GitHub issue + draft PR workflow.
- Queue retries default to `2` attempts with `30s,120s` backoff (`QUEUE_RETRY_*` env vars).
- Default caps:
  - Per job: `$3`, `45m`, `8` iterations.
  - Daily: `$40`, Monthly: `$900`.
- Sensitive path and risk-class changes require human approval.
- Kill switch is backed by Redis key `agents_enabled`.

## Production notes

- Run on Linux host with rootless Docker.
- Restrict control-plane access to LAN + Tailscale.
- Use repo-scoped GitHub App tokens.
- Keep `.env` permissions at `600`.
- Configure backups using `scripts/backup_postgres.sh` (daily, 14-day retention).
- Optional systemd automation: `infra/systemd/codex-backup.service` + `infra/systemd/codex-backup.timer`.

## Additional docs

- `docs/operations_quickstart.md`
- `docs/roadmap.md`
- `docs/runbooks/incidents.md`
- `docs/runbooks/triage_replay.md`
- `docs/kpi_dashboard.md`
- `docs/pi_migration.md`
- `docs/pilot_projects.md`

## Project layout

```text
src/codex_home/      Application code (orchestrator, worker, policy, db)
config/              Policy and repository profiles
infra/               Prometheus/Loki/Grafana/Alertmanager + systemd templates
sql/                 SQL schema bootstrap
scripts/             Host bootstrap and backup scripts
tests/               API and policy tests
```
