# Operations Quickstart

## Start stack

```bash
cp .env.example .env
docker compose up -d --build
```

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

## Create issue + queue job from plain text

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
