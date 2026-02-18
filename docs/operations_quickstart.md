# Operations Quickstart

## Start stack

```bash
cp .env.example .env
docker compose up -d --build
```

## Select run mode

- `RUN_MODE=fast`: local-safe mode. `intake/text` queues jobs without creating GitHub issues or PRs.
- `RUN_MODE=release`: GitHub-integrated mode. `intake/text` creates a GitHub issue and jobs can open draft PRs.

## Create manual job

```bash
curl -X POST "http://localhost:8080/api/v1/jobs" \
  -H "Content-Type: application/json" \
  -H "X-Operator-Token: ${OPERATOR_TOKEN}" \
  -d '{
    "repo": "SydFloyd/KaolCode",
    "issue_number": 123,
    "risk_class": "code",
    "model_profile": "build",
    "created_by": "operator"
  }'
```

## Queue job from plain text

```bash
curl -X POST "http://localhost:8080/api/v1/intake/text" \
  -H "Content-Type: application/json" \
  -H "X-Operator-Token: ${OPERATOR_TOKEN}" \
  -d '{
    "repo": "SydFloyd/KaolCode",
    "title": "Fix flaky test around queue retries",
    "body": "Investigate nondeterministic retry timing and propose a minimal fix.",
    "labels": ["pilot"],
    "risk_class": "code",
    "model_profile": "build",
    "created_by": "operator"
  }'
```

In `release` mode, this endpoint creates a real GitHub issue and uses that issue number.
In `fast` mode, it skips GitHub issue creation and uses a synthetic local issue id.

## Approve gated job

```bash
curl -X POST "http://localhost:8080/api/v1/jobs/<job_id>/approve" \
  -H "Content-Type: application/json" \
  -H "X-Operator-Token: ${OPERATOR_TOKEN}" \
  -d '{
    "action": "infra",
    "actor": "operator",
    "reason": "change reviewed"
  }'
```

## Reject job

```bash
curl -X POST "http://localhost:8080/api/v1/jobs/<job_id>/reject" \
  -H "Content-Type: application/json" \
  -H "X-Operator-Token: ${OPERATOR_TOKEN}" \
  -d '{
    "actor": "operator",
    "reason": "policy mismatch"
  }'
```

## Toggle kill switch

```bash
curl -X POST "http://localhost:8080/api/v1/control/kill-switch" \
  -H "X-Operator-Token: ${OPERATOR_TOKEN}"

curl -X POST "http://localhost:8080/api/v1/control/resume" \
  -H "X-Operator-Token: ${OPERATOR_TOKEN}"
```
