from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest


JOBS_CREATED = Counter("codex_jobs_created_total", "Number of jobs created", ["source"])
JOBS_COMPLETED = Counter("codex_jobs_completed_total", "Number of jobs completed", ["status"])
JOB_FAILURES_TOTAL = Gauge("codex_job_failures_total", "Total number of failed jobs")
JOB_FAILURES_BY_CATEGORY = Gauge(
    "codex_job_failures_by_category",
    "Failed jobs grouped by failure category",
    ["category"],
)
JOB_FAILURES_BY_STAGE = Gauge(
    "codex_job_failures_by_stage",
    "Failed jobs grouped by stage",
    ["stage"],
)
JOB_STAGE_DURATION = Histogram(
    "codex_job_stage_duration_seconds",
    "Duration by job stage",
    ["stage"],
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300, 900, 1800),
)
QUEUE_DEPTH = Gauge("codex_queue_depth", "Current queued jobs")
PENDING_APPROVALS = Gauge("codex_pending_approvals", "Current jobs awaiting approval")
WORKER_HEARTBEAT = Gauge("codex_worker_heartbeat_timestamp", "Last worker heartbeat timestamp")
SPEND_DAILY = Gauge("codex_spend_daily_usd", "Daily spend in USD")
SPEND_MONTHLY = Gauge("codex_spend_monthly_usd", "Monthly spend in USD")
JOB_COST = Counter("codex_job_cost_usd_total", "Total USD spent on jobs")
INCIDENTS = Counter("codex_incidents_total", "Recorded incidents", ["incident_type", "severity"])
AGENTS_ENABLED = Gauge("codex_agents_enabled", "Whether agents are enabled (1=true, 0=false)")


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
