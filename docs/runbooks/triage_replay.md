# Triage and Replay Checklist

Use this checklist when a job fails or stalls.

## 1) Confirm platform state

1. Check orchestrator health:
   - `GET /healthz`
2. Check queue and worker signals:
   - `GET /metrics` and verify:
   - `codex_agents_enabled == 1`
   - `codex_queue_depth` is not growing uncontrollably
   - `codex_worker_heartbeat_timestamp` is recent

## 2) Inspect failed job details

1. Fetch job record:
   - `GET /api/v1/jobs/{job_id}`
2. Capture:
   - `job.status`
   - `job.current_stage`
   - `job.failure_reason`
   - last 3 events from `events`

## 3) Inspect artifacts

1. Open `data/artifacts/{job_id}/run.jsonl`.
2. Open `data/artifacts/{job_id}/test.log` (if present).
3. Open `data/artifacts/{job_id}/review.md` and `patch.diff` (if present).

## 4) Classify and decide

Use `failure_reason` and policy audits to pick one action:

1. `budget_cap`, `command_policy`, `path_policy`, `domain_policy`, `secret_guard`:
   - Fix policy/config first, then replay.
2. `acceptance_test`, `git_failure`, `github_api`, `runtime_error`:
   - Replay once after confirming infra/API health.
3. `approval_gate`:
   - Approve explicitly, then let queue continue.

## 5) Replay safely

Create a replay job from the same issue with explicit operator attribution.

Example:

```bash
curl -X POST "http://localhost:8080/api/v1/jobs" \
  -H "Content-Type: application/json" \
  -H "X-Operator-Token: ${OPERATOR_TOKEN}" \
  -d '{
    "repo": "SydFloyd/KaolCode",
    "issue_number": 123,
    "risk_class": "code",
    "model_profile": "build",
    "created_by": "operator-replay"
  }'
```

## 6) Escalation rules

1. If 3 similar failures happen in 30 minutes:
   - Activate kill switch.
   - Open/append incident record.
2. If failure includes secrets risk:
   - Follow `docs/runbooks/incidents.md` secret exposure playbook immediately.
