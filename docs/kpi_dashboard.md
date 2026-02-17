# KPI Dashboard Spec

## Impact

- `merged_prs_per_week` target `>= 6`
- `maintainer_acceptance_rate` target `>= 60%`
- `median_issue_to_draft_pr_hours` target `<= 6`

## Uptime

- `orchestrator_availability` target `>= 99%`
- `worker_heartbeat_uptime` target `>= 98.5%`
- `job_success_rate` target `>= 80%`

## Utilization

- `desktop_cpu_utilization_during_window` target `50-75%`
- `queue_wait_p95_minutes` target `<= 30`
- `sandbox_slot_utilization` target `60-85%`

## Cost

- `daily_spend_usd` hard cap `40`
- `monthly_spend_usd` hard cap `900`
- `cost_per_merged_pr_usd` target `<= 12`
- `budget_breach_count` target `0`

## Quality

- `first_pass_ci_green_rate` target `>= 70%`
- `post_merge_rollback_rate` target `<= 5%`
- `reopened_issue_rate_14d` target `<= 10%`
