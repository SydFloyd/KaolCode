# Incident Playbooks

## Runaway Cost

1. Trigger: `codex_spend_daily_usd > 40` or abnormal token burn.
2. Containment:
   - `POST /api/v1/control/kill-switch`
   - Rotate LLM API key.
   - Pause webhook delivery in GitHub App settings.
3. Recovery:
   - Inspect last 10 failed/expensive jobs.
   - Patch caps/prompt issue.
   - Run one canary task before resume.
4. Postmortem SLA: publish findings in 24 hours.

## Secret Exposure

1. Trigger: secret scanning hit or suspicious outbound behavior.
2. Containment:
   - Activate kill switch.
   - Revoke and rotate suspected credentials.
   - Quarantine artifact directory for affected jobs.
3. Recovery:
   - Remove leaked values from history/logs.
   - Re-issue clean PRs.
   - Add new pattern to `config/policy.yaml:secret_patterns`.

## Unsafe Infra Change Attempt

1. Trigger: diff intersects sensitive paths without approval.
2. Containment:
   - Reject job via `POST /api/v1/jobs/{id}/reject`.
   - Record incident in `incidents`.
3. Recovery:
   - Add failing regression test for policy rule.
   - Re-run job under explicit infra approval.

## Worker Downtime

1. Trigger: no worker heartbeat > 5 minutes.
2. Containment:
   - Restart worker service/container.
   - Check Redis and Postgres health.
3. Recovery:
   - Replay queued jobs.
   - Document root cause and prevention.
