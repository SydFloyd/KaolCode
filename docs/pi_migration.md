# Pi Migration Sequence (Phase B)

## Target split

- Pi-1: orchestrator API + scheduler + Redis
- Pi-2: Prometheus + Loki + Grafana + Alertmanager
- Pi-3: backup target + hot spare
- Desktop: worker + sandbox execution

## Steps

1. Provision Ubuntu 24.04 on each Pi and attach SSD storage.
2. Install Docker + Tailscale + UFW with LAN/Tailnet-only access.
3. Move `redis` and `orchestrator` services to Pi-1:
   - Update `REDIS_URL` and `DATABASE_URL` in `.env`.
   - Validate webhook intake and queue operations.
4. Move observability stack to Pi-2:
   - Point Prometheus scrape target to orchestrator.
   - Point Grafana datasources to Pi-2 local services.
5. Enable daily Postgres backups to Pi-3:
   - Schedule `scripts/backup_postgres.sh` via cron/systemd timer.
   - Keep 14-day retention.
6. Execute failover drill:
   - Stop desktop worker for 10 minutes.
   - Verify queue/state persistence and controlled recovery.
