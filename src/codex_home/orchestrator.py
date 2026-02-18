from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import uvicorn
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request, Response, status

from codex_home.config import Settings, get_settings
from codex_home.db import build_engine, build_session_factory, init_db
from codex_home.failure_taxonomy import classify_failure_reason
from codex_home.github_api import GitHubAppClient
from codex_home.logging_utils import configure_logging
from codex_home.metrics import (
    AGENTS_ENABLED,
    JOBS_CREATED,
    JOB_FAILURES_BY_CATEGORY,
    JOB_FAILURES_BY_STAGE,
    JOB_FAILURES_TOTAL,
    PENDING_APPROVALS,
    QUEUE_DEPTH,
    render_metrics,
)
from codex_home.policy import load_policy, load_repo_profiles
from codex_home.queueing import agents_enabled, build_redis, enqueue_job, queue_size, set_kill_switch
from codex_home.repository import Repository
from codex_home.security import operator_auth_dependency, verify_github_signature
from codex_home.types import (
    ApprovalRequest,
    JobCreateRequest,
    JobResponse,
    JobSpecV1,
    JobStatus,
    RejectRequest,
    RiskClass,
    TextIntakeRequest,
    WebhookResult,
)


logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _local_issue_number() -> int:
    # Synthetic issue id for fast-mode intake jobs that do not create GitHub issues.
    return int(uuid4().int % 2_000_000_000) + 1


def _detect_risk(labels: list[str]) -> RiskClass:
    if "destructive" in labels:
        return RiskClass.DESTRUCTIVE
    if "secrets" in labels:
        return RiskClass.SECRETS
    if "infra" in labels:
        return RiskClass.INFRA
    if "deps" in labels or "dependencies" in labels or "security" in labels:
        return RiskClass.DEPS
    return RiskClass.CODE


def _build_job_response(job) -> JobResponse:
    return JobResponse(
        job_id=UUID(job.job_id),
        status=JobStatus(job.status),
        repo=job.repo,
        issue_number=job.issue_number,
        risk_class=RiskClass(job.risk_class),
        current_stage=job.current_stage,
        pr_url=job.pr_url,
        failure_reason=job.failure_reason,
        created_at=job.created_at,
        updated_at=job.updated_at,
        cost_usd=float(job.cost_usd),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="Codex Home Orchestrator", version="0.1.0")

    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    if settings.auto_migrate:
        init_db(engine)

    policy = load_policy(settings.policy_path)
    repo_profiles = load_repo_profiles(settings.repos_path)
    redis_client = build_redis(settings)
    with session_factory() as session:
        repository = Repository(session)
        repository.upsert_repo_profiles(repo_profiles)

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.policy = policy
    app.state.redis = redis_client
    AGENTS_ENABLED.set(1 if agents_enabled(redis_client) else 0)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics")
    def metrics() -> Response:
        with session_factory() as session:
            repository = Repository(session)
            PENDING_APPROVALS.set(repository.pending_approval_count())
            failed_jobs = repository.list_failed_jobs(limit=5000)

        category_counts: dict[str, int] = {}
        stage_counts: dict[str, int] = {}
        for failed in failed_jobs:
            category = classify_failure_reason(failed.failure_reason)
            stage = failed.current_stage or "unknown"
            category_counts[category] = category_counts.get(category, 0) + 1
            stage_counts[stage] = stage_counts.get(stage, 0) + 1

        JOB_FAILURES_TOTAL.set(len(failed_jobs))
        JOB_FAILURES_BY_CATEGORY.clear()
        for category, count in category_counts.items():
            JOB_FAILURES_BY_CATEGORY.labels(category=category).set(count)
        JOB_FAILURES_BY_STAGE.clear()
        for stage, count in stage_counts.items():
            JOB_FAILURES_BY_STAGE.labels(stage=stage).set(count)

        QUEUE_DEPTH.set(queue_size(settings, redis_client))
        AGENTS_ENABLED.set(1 if agents_enabled(redis_client) else 0)
        payload, content_type = render_metrics()
        return Response(content=payload, media_type=content_type)

    @app.post("/api/v1/webhooks/github", response_model=WebhookResult)
    async def github_webhook(
        request: Request,
        x_github_event: str | None = Header(default=None),
        x_hub_signature_256: str | None = Header(default=None),
    ) -> WebhookResult:
        body = await request.body()
        if not verify_github_signature(body, x_hub_signature_256, settings.webhook_secret):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature.")

        if not agents_enabled(redis_client):
            return WebhookResult(accepted=False, message="Kill switch active.")

        if x_github_event != "issues":
            return WebhookResult(accepted=False, message="Event ignored.")

        payload = json.loads(body.decode("utf-8"))
        action = payload.get("action")
        repo_name = payload.get("repository", {}).get("full_name", "")
        issue = payload.get("issue", {})
        issue_number = issue.get("number")
        labels = [entry.get("name", "").lower() for entry in issue.get("labels", [])]
        is_agent_ready = "agent-ready" in labels
        if action == "labeled":
            labeled = payload.get("label", {}).get("name", "").lower()
            is_agent_ready = labeled == "agent-ready"

        if not is_agent_ready:
            return WebhookResult(accepted=False, message="Missing agent-ready label.")
        if not policy.repo_allowed(repo_name):
            return WebhookResult(accepted=False, message=f"Repo not allowlisted: {repo_name}")
        if not issue_number:
            return WebhookResult(accepted=False, message="Missing issue number.")

        risk = _detect_risk(labels)
        with session_factory() as session:
            repository = Repository(session)
            profile = repository.get_repo_profile(repo_name)
            if not profile or not profile.enabled:
                return WebhookResult(accepted=False, message=f"Repo disabled: {repo_name}")

            latest = repository.latest_job_for_issue(repo_name, int(issue_number))
            if latest:
                if latest.status in {
                    JobStatus.QUEUED.value,
                    JobStatus.RUNNING.value,
                    JobStatus.AWAITING_APPROVAL.value,
                }:
                    return WebhookResult(accepted=False, message=f"Job already in progress: {latest.job_id}")
                if latest.created_at >= (_utc_now() - timedelta(minutes=2)):
                    return WebhookResult(accepted=False, message=f"Duplicate webhook ignored: {latest.job_id}")

            spec = JobSpecV1(
                repo=repo_name,
                issue_number=int(issue_number),
                base_branch=profile.default_base_branch,
                risk_class=risk,
                allowed_paths=profile.allowed_paths,
                acceptance_commands=profile.acceptance_commands,
                caps=policy.default_caps,
                requires_approval=policy.required_approvals(risk),
                created_by="github-webhook",
            )
            created = repository.create_job(spec)
            enqueue_job(settings, redis_client, created.job_id)
            JOBS_CREATED.labels(source="webhook").inc()
            logger.info("Job created from webhook", extra={"job_id": created.job_id})
            return WebhookResult(accepted=True, message="Job queued.", job_id=UUID(created.job_id))

    @app.post(
        "/api/v1/jobs",
        response_model=JobResponse,
        dependencies=[Depends(operator_auth_dependency)],
    )
    def create_job(job_request: JobCreateRequest = Body(...)) -> JobResponse:
        if not policy.repo_allowed(job_request.repo):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Repo not in allowlist.")

        with session_factory() as session:
            repository = Repository(session)
            profile = repository.get_repo_profile(job_request.repo)
            if not profile or not profile.enabled:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repo profile not enabled.")

            caps = job_request.caps or policy.default_caps
            spec = JobSpecV1(
                repo=job_request.repo,
                issue_number=job_request.issue_number,
                base_branch=job_request.base_branch or profile.default_base_branch,
                risk_class=job_request.risk_class,
                model_profile=job_request.model_profile,
                allowed_paths=job_request.allowed_paths or profile.allowed_paths,
                acceptance_commands=job_request.acceptance_commands or profile.acceptance_commands,
                caps=caps,
                requires_approval=policy.required_approvals(job_request.risk_class),
                created_by=job_request.created_by,
                created_at=_utc_now(),
            )
            created = repository.create_job(spec)
            enqueue_job(settings, redis_client, created.job_id)
            JOBS_CREATED.labels(source="manual").inc()
            return _build_job_response(created)

    @app.post(
        "/api/v1/intake/text",
        response_model=JobResponse,
        dependencies=[Depends(operator_auth_dependency)],
    )
    def intake_text(payload: TextIntakeRequest = Body(...)) -> JobResponse:
        if not policy.repo_allowed(payload.repo):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Repo not in allowlist.")

        labels = sorted({label for label in payload.labels if label.lower() != "agent-ready"})
        if settings.is_release_mode():
            github = GitHubAppClient(settings)
            try:
                issue = github.create_issue(
                    repo=payload.repo,
                    title=payload.title,
                    body=payload.body,
                    labels=labels,
                )
                issue_number = int(issue.number)
            except RuntimeError as exc:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        else:
            issue_number = _local_issue_number()

        with session_factory() as session:
            repository = Repository(session)
            profile = repository.get_repo_profile(payload.repo)
            if not profile or not profile.enabled:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repo profile not enabled.")

            caps = payload.caps or policy.default_caps
            spec = JobSpecV1(
                repo=payload.repo,
                issue_number=issue_number,
                base_branch=payload.base_branch or profile.default_base_branch,
                risk_class=payload.risk_class,
                model_profile=payload.model_profile,
                allowed_paths=payload.allowed_paths or profile.allowed_paths,
                acceptance_commands=payload.acceptance_commands or profile.acceptance_commands,
                caps=caps,
                requires_approval=policy.required_approvals(payload.risk_class),
                created_by=payload.created_by,
                created_at=_utc_now(),
            )
            created = repository.create_job(spec)
            enqueue_job(settings, redis_client, created.job_id)
            source = "text_intake_release" if settings.is_release_mode() else "text_intake_fast"
            JOBS_CREATED.labels(source=source).inc()
            return _build_job_response(created)

    @app.get(
        "/api/v1/jobs/{job_id}",
        dependencies=[Depends(operator_auth_dependency)],
    )
    def get_job(job_id: UUID) -> dict[str, Any]:
        with session_factory() as session:
            repository = Repository(session)
            job = repository.get_job(str(job_id))
            if not job:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
            events = repository.list_job_events(str(job_id))
            return {
                "job": _build_job_response(job).model_dump(),
                "events": [
                    {
                        "stage": event.stage,
                        "event_type": event.event_type,
                        "message": event.message,
                        "metadata": event.metadata_json,
                        "created_at": event.created_at,
                    }
                    for event in events
                ],
            }

    @app.post(
        "/api/v1/jobs/{job_id}/approve",
        dependencies=[Depends(operator_auth_dependency)],
    )
    def approve_job(job_id: UUID, payload: ApprovalRequest) -> dict[str, str]:
        with session_factory() as session:
            repository = Repository(session)
            job = repository.get_job(str(job_id))
            if not job:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
            repository.add_approval(
                str(job_id),
                payload.action,
                actor=payload.actor,
                approved=True,
                reason=payload.reason,
            )
            repository.add_job_event(
                str(job_id),
                "approval",
                "approved",
                f"{payload.action.value} approved by {payload.actor}.",
            )
            if job.status == JobStatus.AWAITING_APPROVAL.value:
                repository.update_job_status(job, JobStatus.QUEUED, stage="approval")
                enqueue_job(settings, redis_client, job.job_id)
        return {"status": "approved"}

    @app.post(
        "/api/v1/jobs/{job_id}/reject",
        dependencies=[Depends(operator_auth_dependency)],
    )
    def reject_job(job_id: UUID, payload: RejectRequest) -> dict[str, str]:
        with session_factory() as session:
            repository = Repository(session)
            job = repository.get_job(str(job_id))
            if not job:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
            repository.update_job_status(job, JobStatus.REJECTED, stage="approval", reason=payload.reason)
            repository.add_job_event(str(job_id), "approval", "rejected", f"Rejected by {payload.actor}: {payload.reason}")
        return {"status": "rejected"}

    @app.post(
        "/api/v1/control/kill-switch",
        dependencies=[Depends(operator_auth_dependency)],
    )
    def kill_switch() -> dict[str, str]:
        set_kill_switch(redis_client, enabled=False)
        AGENTS_ENABLED.set(0)
        with session_factory() as session:
            repository = Repository(session)
            repository.add_incident("kill_switch", "warning", "open", "Kill switch manually activated.")
        return {"status": "disabled"}

    @app.post(
        "/api/v1/control/resume",
        dependencies=[Depends(operator_auth_dependency)],
    )
    def resume() -> dict[str, str]:
        set_kill_switch(redis_client, enabled=True)
        AGENTS_ENABLED.set(1)
        with session_factory() as session:
            repository = Repository(session)
            repository.add_incident("kill_switch", "info", "closed", "Execution resumed.")
        return {"status": "enabled"}

    return app


def main() -> None:
    settings = get_settings()
    app = create_app(settings)
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    main()
