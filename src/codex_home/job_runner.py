from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

from codex_home.artifacts import append_jsonl, ensure_contract, ensure_job_artifact_dir, write_text
from codex_home.config import get_settings
from codex_home.db import build_engine, build_session_factory
from codex_home.llm import LLMClient
from codex_home.logging_utils import configure_logging
from codex_home.metrics import JOBS_COMPLETED, JOB_COST, JOB_STAGE_DURATION, SPEND_DAILY, SPEND_MONTHLY, WORKER_HEARTBEAT
from codex_home.policy import load_policy
from codex_home.queueing import agents_enabled, build_redis
from codex_home.repository import Repository
from codex_home.types import ApprovalAction, JobStatus, RiskClass


logger = logging.getLogger(__name__)
URL_PATTERN = re.compile(r"https?://[^\s'\"`]+")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _run_stage(name: str, fn):
    start = time.monotonic()
    try:
        return fn()
    finally:
        JOB_STAGE_DURATION.labels(stage=name).observe(time.monotonic() - start)


def _run_command(command: str, timeout_seconds: int, cwd: Path, dry_run: bool) -> tuple[int, str]:
    if dry_run:
        return 0, f"DRY_RUN validated command: {command}\n"

    if shutil.which("docker"):
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--read-only",
            "--network",
            "none",
            "--cpus",
            "4",
            "--memory",
            "8g",
            "--pids-limit",
            "512",
            "-v",
            f"{cwd.absolute()}:/workspace",
            "-w",
            "/workspace",
            "python:3.12-slim",
            "bash",
            "-lc",
            command,
        ]
        proc = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return int(proc.returncode), (proc.stdout + proc.stderr)

    proc = subprocess.run(
        command,
        cwd=str(cwd),
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return int(proc.returncode), (proc.stdout + proc.stderr)


def _require_approval(repo: Repository, job_id: str, risk_class: str) -> bool:
    if risk_class == RiskClass.INFRA.value:
        return repo.has_approval(job_id, ApprovalAction.INFRA)
    if risk_class == RiskClass.SECRETS.value:
        return repo.has_approval(job_id, ApprovalAction.SECRETS)
    if risk_class == RiskClass.DESTRUCTIVE.value:
        return repo.has_approval(job_id, ApprovalAction.DESTRUCTIVE)
    return True


def _check_spend_caps(repo: Repository, settings, job) -> None:
    if job is None:
        raise RuntimeError("JOB_NOT_FOUND")
    today = date.today().isoformat()
    month = date.today().strftime("%Y-%m")
    daily = repo.daily_cost(today)
    monthly = repo.monthly_cost(month)
    SPEND_DAILY.set(daily)
    SPEND_MONTHLY.set(monthly)
    if daily > settings.max_usd_per_day:
        raise RuntimeError("CAP_DAILY_BUDGET_EXCEEDED")
    if monthly > settings.max_usd_per_month:
        raise RuntimeError("CAP_MONTHLY_BUDGET_EXCEEDED")
    if float(job.cost_usd) > float(job.caps_max_usd):
        raise RuntimeError("CAP_COST_EXCEEDED")


def process_job(job_id: str) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    WORKER_HEARTBEAT.set(time.time())

    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    policy = load_policy(settings.policy_path)
    redis_client = build_redis(settings)
    llm = LLMClient(settings)

    with session_factory() as session:
        repo = Repository(session)
        job = repo.get_job(job_id)
        if not job:
            logger.error("Job not found", extra={"job_id": job_id})
            return

        artifact_dir = ensure_job_artifact_dir(settings.artifact_root, job_id)
        ensure_contract(artifact_dir, job.artifact_contract)
        run_log = artifact_dir / "run.jsonl"

        append_jsonl(
            run_log,
            {
                "ts": _utc_now().isoformat(),
                "event": "job_start",
                "job_id": job_id,
                "status": job.status,
            },
        )

        if not agents_enabled(redis_client):
            repo.update_job_status(job, JobStatus.FAILED, stage="dispatch", reason="KILL_SWITCH_ACTIVE")
            repo.add_job_event(job_id, "dispatch", "failed", "Kill switch active.")
            JOBS_COMPLETED.labels(status=JobStatus.FAILED.value).inc()
            return

        if job.status in {JobStatus.COMPLETED.value, JobStatus.REJECTED.value}:
            return

        if not _require_approval(repo, job_id, job.risk_class):
            repo.update_job_status(job, JobStatus.AWAITING_APPROVAL, stage="approval")
            repo.add_job_event(
                job_id,
                "approval",
                "waiting",
                f"Approval required for risk class {job.risk_class}.",
            )
            return

        repo.update_job_status(job, JobStatus.RUNNING, stage="triage")
        append_jsonl(run_log, {"ts": _utc_now().isoformat(), "event": "stage_start", "stage": "triage"})

        try:
            def triage_stage():
                triage = llm.generate(
                    settings.model_triage,
                    (
                        "Produce a concise triage summary for this issue.\n"
                        f"Repo: {job.repo}\nIssue: {job.issue_number}\nRisk: {job.risk_class}"
                    ),
                )
                repo.add_cost(job_id, triage.model, triage.prompt_tokens, triage.completion_tokens, triage.cost_usd)
                JOB_COST.inc(triage.cost_usd)
                write_text(
                    artifact_dir / "plan.md",
                    (
                        f"# Job {job_id}\n\n"
                        "## Triage\n"
                        f"- Repo: `{job.repo}`\n"
                        f"- Issue: `{job.issue_number}`\n"
                        f"- Risk: `{job.risk_class}`\n\n"
                        f"{triage.content}\n"
                    ),
                )
                repo.add_job_event(job_id, "triage", "completed", "Triage completed.")

            _run_stage("triage", triage_stage)
            _check_spend_caps(repo, settings, repo.get_job(job_id))
            repo.update_job_status(job, JobStatus.RUNNING, stage="plan")

            def plan_stage():
                plan = llm.generate(
                    settings.model_build,
                    "Generate a concrete execution checklist and expected tests for this task.",
                )
                repo.add_cost(job_id, plan.model, plan.prompt_tokens, plan.completion_tokens, plan.cost_usd)
                JOB_COST.inc(plan.cost_usd)
                existing = (artifact_dir / "plan.md").read_text(encoding="utf-8")
                write_text(artifact_dir / "plan.md", existing + "\n## Execution Checklist\n" + plan.content + "\n")
                repo.add_job_event(job_id, "plan", "completed", "Planning completed.")

            _run_stage("plan", plan_stage)
            _check_spend_caps(repo, settings, repo.get_job(job_id))
            repo.update_job_status(job, JobStatus.RUNNING, stage="execute")

            def execute_stage():
                changed_paths = ["README.md"]
                violations = policy.allowed_path_violation(changed_paths, job.allowed_paths or ["**"])
                if violations:
                    repo.add_policy_audit(
                        job_id,
                        "deny",
                        "allowed_paths",
                        f"Attempted paths outside allowlist: {', '.join(violations)}",
                    )
                    raise RuntimeError("ALLOWED_PATHS_VIOLATION")

                if policy.requires_sensitive_approval(changed_paths) and not repo.has_approval(job_id, ApprovalAction.INFRA):
                    repo.update_job_status(job, JobStatus.AWAITING_APPROVAL, stage="execute")
                    repo.add_job_event(job_id, "execute", "waiting", "Sensitive paths require infra approval.")
                    raise RuntimeError("SENSITIVE_PATH_APPROVAL_REQUIRED")

                patch = (
                    "--- a/README.md\n"
                    "+++ b/README.md\n"
                    "@@\n"
                    "+# Agent run summary\n"
                    "+Generated patch placeholder for draft PR context.\n"
                )
                write_text(artifact_dir / "patch.diff", patch)
                repo.add_policy_audit(job_id, "allow", "allowed_paths", "Changed paths validated.")
                repo.add_job_event(job_id, "execute", "completed", "Execution stage produced patch artifact.")

            _run_stage("execute", execute_stage)
            job = repo.get_job(job_id)
            if job and job.status == JobStatus.AWAITING_APPROVAL.value:
                return

            repo.update_job_status(job, JobStatus.RUNNING, stage="test")

            def test_stage():
                outputs: list[str] = []
                with tempfile.TemporaryDirectory(prefix=f"codex_job_{job_id}_") as tmpdir:
                    tmp_path = Path(tmpdir)
                    for command in job.acceptance_commands:
                        if policy.is_blocked_command(command):
                            repo.add_policy_audit(job_id, "deny", "blocked_command", command)
                            raise RuntimeError(f"BLOCKED_COMMAND: {command}")
                        for url in URL_PATTERN.findall(command):
                            if not policy.domain_allowed(url):
                                repo.add_policy_audit(job_id, "deny", "domain_allowlist", url)
                                raise RuntimeError(f"DOMAIN_NOT_ALLOWLISTED: {url}")

                        code, output = _run_command(
                            command=command,
                            timeout_seconds=min(job.caps_max_minutes * 60, 1200),
                            cwd=tmp_path,
                            dry_run=settings.dry_run,
                        )
                        outputs.append(f"$ {command}\n{output}\n")
                        if code != 0:
                            raise RuntimeError(f"ACCEPTANCE_COMMAND_FAILED: {command}")
                write_text(artifact_dir / "test.log", "\n".join(outputs))
                repo.add_job_event(job_id, "test", "completed", "Acceptance commands completed.")

            _run_stage("test", test_stage)
            repo.update_job_status(job, JobStatus.RUNNING, stage="review")

            def review_stage():
                review = llm.generate(
                    settings.model_review,
                    "Write concise PR review notes emphasizing risk, tests, and rollback guidance.",
                )
                repo.add_cost(job_id, review.model, review.prompt_tokens, review.completion_tokens, review.cost_usd)
                JOB_COST.inc(review.cost_usd)
                if policy.secrets_detected(review.content):
                    raise RuntimeError("SECRET_PATTERN_DETECTED_IN_REVIEW")
                write_text(artifact_dir / "review.md", review.content + "\n")
                repo.add_job_event(job_id, "review", "completed", "Review notes generated.")

            _run_stage("review", review_stage)
            _check_spend_caps(repo, settings, repo.get_job(job_id))
            repo.update_job_status(job, JobStatus.RUNNING, stage="pr")

            def pr_stage():
                pr_url = f"https://github.com/{job.repo}/pull/{job.issue_number}"
                write_text(
                    artifact_dir / "cost.json",
                    json.dumps(
                        {
                            "job_id": job_id,
                            "daily_cap": settings.max_usd_per_day,
                            "monthly_cap": settings.max_usd_per_month,
                            "job_cost_usd": float(repo.get_job(job_id).cost_usd),  # type: ignore[union-attr]
                        },
                        ensure_ascii=True,
                        indent=2,
                    ),
                )
                repo.add_job_event(job_id, "pr", "completed", "Draft PR prepared.")
                repo.update_job_status(job, JobStatus.COMPLETED, stage="pr", pr_url=pr_url)

            _run_stage("pr", pr_stage)
            JOBS_COMPLETED.labels(status=JobStatus.COMPLETED.value).inc()
            append_jsonl(run_log, {"ts": _utc_now().isoformat(), "event": "job_completed"})

        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            logger.exception("Job failed", extra={"job_id": job_id})
            latest_job = repo.get_job(job_id)
            if latest_job and latest_job.status != JobStatus.AWAITING_APPROVAL.value:
                repo.update_job_status(latest_job, JobStatus.FAILED, stage=latest_job.current_stage, reason=message)
                repo.add_job_event(job_id, latest_job.current_stage or "unknown", "failed", message)
                JOBS_COMPLETED.labels(status=JobStatus.FAILED.value).inc()
            append_jsonl(run_log, {"ts": _utc_now().isoformat(), "event": "job_failed", "error": message})
