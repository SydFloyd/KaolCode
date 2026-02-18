from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from codex_home.models import Approval, CostLedger, Incident, Job, JobEvent, PolicyAudit, RepoProfile
from codex_home.types import ApprovalAction, JobSpecV1, JobStatus


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def create_job(self, spec: JobSpecV1) -> Job:
        job = Job(
            job_id=str(spec.job_id),
            repo=spec.repo,
            issue_number=spec.issue_number,
            base_branch=spec.base_branch,
            risk_class=spec.risk_class.value,
            status=JobStatus.QUEUED.value,
            model_profile=spec.model_profile.value,
            requires_approval=[action.value for action in spec.requires_approval],
            allowed_paths=spec.allowed_paths,
            acceptance_commands=spec.acceptance_commands,
            artifact_contract=spec.artifact_contract,
            caps_max_minutes=spec.caps.max_minutes,
            caps_max_iterations=spec.caps.max_iterations,
            caps_max_usd=spec.caps.max_usd,
            created_by=spec.created_by,
            created_at=spec.created_at.replace(tzinfo=timezone.utc),
            updated_at=spec.created_at.replace(tzinfo=timezone.utc),
        )
        self.session.add(job)
        self.session.flush()
        self.add_job_event(
            job.job_id,
            stage="enqueue",
            event_type="created",
            message="Job created and queued.",
            metadata={"source": spec.created_by},
        )
        self.session.commit()
        return job

    def get_job(self, job_id: str) -> Job | None:
        return self.session.get(Job, job_id)

    def latest_job_for_issue(self, repo: str, issue_number: int) -> Job | None:
        stmt = (
            select(Job)
            .where(Job.repo == repo)
            .where(Job.issue_number == issue_number)
            .order_by(desc(Job.created_at))
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def list_job_events(self, job_id: str) -> list[JobEvent]:
        stmt = select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.created_at.asc())
        return list(self.session.execute(stmt).scalars())

    def update_job_status(
        self,
        job: Job,
        status: JobStatus,
        stage: str | None = None,
        reason: str | None = None,
        pr_url: str | None = None,
    ) -> Job:
        job.status = status.value
        job.updated_at = datetime.now(timezone.utc)
        if stage is not None:
            job.current_stage = stage
        if reason:
            job.failure_reason = reason
        if pr_url is not None:
            job.pr_url = pr_url
        self.session.add(job)
        self.session.commit()
        return job

    def add_job_event(
        self,
        job_id: str,
        stage: str,
        event_type: str,
        message: str,
        metadata: dict | None = None,
    ) -> JobEvent:
        event = JobEvent(
            job_id=job_id,
            stage=stage,
            event_type=event_type,
            message=message,
            metadata_json=metadata,
        )
        self.session.add(event)
        self.session.commit()
        return event

    def add_approval(
        self,
        job_id: str,
        action: ApprovalAction,
        actor: str,
        approved: bool = True,
        reason: str | None = None,
    ) -> Approval:
        entry = Approval(
            job_id=job_id,
            action=action.value,
            actor=actor,
            approved=approved,
            reason=reason,
        )
        self.session.add(entry)
        self.session.commit()
        return entry

    def has_approval(self, job_id: str, action: ApprovalAction) -> bool:
        stmt = (
            select(Approval)
            .where(Approval.job_id == job_id)
            .where(Approval.action == action.value)
            .where(Approval.approved.is_(True))
            .order_by(desc(Approval.created_at))
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def add_policy_audit(self, job_id: str, decision: str, rule_id: str, details: str) -> PolicyAudit:
        audit = PolicyAudit(job_id=job_id, decision=decision, rule_id=rule_id, details=details)
        self.session.add(audit)
        self.session.commit()
        return audit

    def add_cost(
        self,
        job_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
    ) -> CostLedger:
        record = CostLedger(
            job_id=job_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )
        self.session.add(record)

        job = self.get_job(job_id)
        if job:
            job.cost_usd = float(job.cost_usd) + cost_usd
            job.updated_at = datetime.now(timezone.utc)
            self.session.add(job)
        self.session.commit()
        return record

    def daily_cost(self, day_iso: str | None = None) -> float:
        target = date.fromisoformat(day_iso) if day_iso else date.today()
        stmt = select(CostLedger)
        total = 0.0
        for row in self.session.execute(stmt).scalars():
            if row.created_at.date() == target:
                total += float(row.cost_usd)
        return total

    def monthly_cost(self, month_prefix: str | None = None) -> float:
        if month_prefix:
            year, month = month_prefix.split("-")
            target_year = int(year)
            target_month = int(month)
        else:
            now = datetime.now(timezone.utc)
            target_year = now.year
            target_month = now.month
        stmt = select(CostLedger)
        total = 0.0
        for row in self.session.execute(stmt).scalars():
            if row.created_at.year == target_year and row.created_at.month == target_month:
                total += float(row.cost_usd)
        return total

    def add_incident(self, incident_type: str, severity: str, status: str, details: str) -> Incident:
        incident = Incident(
            incident_type=incident_type,
            severity=severity,
            status=status,
            details=details,
        )
        self.session.add(incident)
        self.session.commit()
        return incident

    def upsert_repo_profiles(self, profiles: dict[str, dict]) -> None:
        for repo_name, profile in profiles.items():
            existing = self.session.get(RepoProfile, repo_name)
            if existing:
                existing.enabled = bool(profile.get("enabled", True))
                existing.default_base_branch = profile.get("base_branch", "main")
                existing.allowed_paths = list(profile.get("allowed_paths", []))
                existing.acceptance_commands = list(profile.get("acceptance_commands", []))
                existing.updated_at = datetime.now(timezone.utc)
                self.session.add(existing)
            else:
                self.session.add(
                    RepoProfile(
                        repo=repo_name,
                        enabled=bool(profile.get("enabled", True)),
                        default_base_branch=profile.get("base_branch", "main"),
                        allowed_paths=list(profile.get("allowed_paths", [])),
                        acceptance_commands=list(profile.get("acceptance_commands", [])),
                    )
                )
        self.session.commit()

    def get_repo_profile(self, repo: str) -> RepoProfile | None:
        return self.session.get(RepoProfile, repo)

    def pending_approval_count(self) -> int:
        stmt = select(Job).where(Job.status == JobStatus.AWAITING_APPROVAL.value)
        return len(list(self.session.execute(stmt).scalars()))

    def queue_depth(self) -> int:
        stmt = select(Job).where(Job.status == JobStatus.QUEUED.value)
        return len(list(self.session.execute(stmt).scalars()))

    def list_recent_failures(self, limit: int = 10) -> Iterable[Job]:
        stmt = (
            select(Job)
            .where(Job.status == JobStatus.FAILED.value)
            .order_by(desc(Job.updated_at))
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())
