# Codex-at-Home Roadmap

## Goal

Build a high-uptime, safety-first coding-agent platform that delivers real external value first (accepted PRs, fixed CI, reduced maintainer toil), with controlled autonomy.

## Operating Rules

- Human approval is required for merges, secrets changes, infra changes, and destructive actions.
- Hard caps are always on: runtime, iteration, per-job spend, daily spend, monthly spend.
- Work is queue-driven and artifact-backed, not open-ended prompting.
- At least 80% of job volume must be external-value tasks.

## Milestones

### 1) Baseline Lock (Now)

Objective:
- Freeze a stable safety baseline and remove experimental UX detours.

Deliverables:
- `RUN_MODE` split enforced (`fast`, `release`).
- `fast` mode has no GitHub issue/PR writes.
- Single pilot repo scope (`SydFloyd/KaolCode`).
- Conservative queue parallelism (`max_parallel_jobs: 1`).
- Roadmap and ops docs aligned with current behavior.

Exit criteria:
- Tests pass (`pytest`, `ruff`, `compileall`).
- Fast-mode smoke run completes with artifacts and no PR URL.

### 2) Fast Lane Hardening (Week 1)

Objective:
- Run cheap, local, high-frequency jobs to tighten reliability.

Deliverables:
- Failure taxonomy dashboard panel.
- Retry policy tuned for queue and worker restarts.
- Operator checklist for triage/replay.

Exit criteria:
- 20/20 fast jobs complete with zero unsafe events.

### 3) Release Lane Validation (Week 2)

Objective:
- Turn external value into the default outcome.

Deliverables:
- Release-mode runbook.
- 5 real draft PR attempts in pilot repo.
- Review templates standardized.

Exit criteria:
- Maintainer acceptance rate >= 60% over first 5 PRs.

### 4) Quality Uplift (Week 3)

Objective:
- Improve first-pass CI and reduce reruns.

Deliverables:
- Per-repo acceptance command profiles.
- Stronger regression-test expectations in review artifacts.

Exit criteria:
- First-pass CI green rate >= 70%.

### 5) Throughput Uplift (Week 4-5)

Objective:
- Increase throughput without losing safety or quality.

Deliverables:
- Priority scoring for queue dispatch.
- Controlled increase to `max_parallel_jobs: 2` after stability gate.

Exit criteria:
- Queue wait p95 <= 30 minutes at target load.

### 6) Pi Control Plane Split (Week 6-7)

Objective:
- Remove desktop single-point control-plane risk.

Deliverables:
- Orchestrator + Redis moved to Pi node.
- Monitoring stack moved to Pi node.
- Backup and restore run validated.

Exit criteria:
- Desktop worker restart does not lose queue/state integrity.

### 7) Agent Family Phase (Week 8+)

Objective:
- Add bounded multi-agent roles (planner/executor/reviewer) for higher leverage.

Deliverables:
- Role-specific prompts and policy constraints.
- Job-level role traceability in artifacts.

Exit criteria:
- Sustained merged-PR cadence with no approval bypass incidents.

## KPI Gates

- `maintainer_acceptance_rate >= 60%`
- `job_success_rate >= 80%`
- `queue_wait_p95_minutes <= 30`
- `daily_spend_usd <= 40`
- `monthly_spend_usd <= 900`
- `budget_breach_count = 0`

## Current Focus

Active milestone: `1) Baseline Lock`.

