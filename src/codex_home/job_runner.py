from __future__ import annotations

import base64
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
from codex_home.github_api import GitHubAppClient
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


def _run_command(command: str, timeout_seconds: int, cwd: Path, fast_mode: bool) -> tuple[int, str]:
    if fast_mode:
        return 0, f"FAST_MODE validated command: {command}\n"

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


def _run_host_command(command: list[str], timeout_seconds: int, cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return int(proc.returncode), (proc.stdout + proc.stderr)


def _run_git_command(
    args: list[str],
    timeout_seconds: int,
    cwd: Path,
    auth_token: str | None = None,
) -> tuple[int, str]:
    command = ["git"]
    if auth_token:
        basic = base64.b64encode(f"x-access-token:{auth_token}".encode("utf-8")).decode("utf-8")
        command.extend(["-c", f"http.extraheader=Authorization: Basic {basic}"])
    command.extend(args)
    return _run_host_command(command, timeout_seconds=timeout_seconds, cwd=cwd)


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
    fast_mode = settings.is_fast_mode()

    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    policy = load_policy(settings.policy_path)
    redis_client = build_redis(settings)
    llm = LLMClient(settings)
    github = GitHubAppClient(settings)

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

        issue_title = f"Issue #{job.issue_number}"
        issue_body = ""
        issue_url = ""
        branch_name = f"codex-home/job-{job_id[:8]}-{int(time.time())}"
        changed_paths: list[str] = []

        try:
            if settings.is_release_mode():
                issue = github.get_issue(job.repo, job.issue_number)
                issue_title = issue.title or issue_title
                issue_body = issue.body or ""
                issue_url = issue.html_url or ""

            with tempfile.TemporaryDirectory(prefix=f"codex_job_{job_id}_") as tmpdir:
                workspace_root = Path(tmpdir)
                repo_workspace = workspace_root / "repo"

                def triage_stage() -> None:
                    issue_excerpt = issue_body[:2000] if issue_body else "(no issue body provided)"
                    triage = llm.generate(
                        settings.model_triage,
                        (
                            "Produce a concise triage summary for this issue.\n"
                            f"Repo: {job.repo}\nIssue: {job.issue_number}\nRisk: {job.risk_class}\n"
                            f"Issue title: {issue_title}\n"
                            f"Issue body:\n{issue_excerpt}"
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
                            f"- Risk: `{job.risk_class}`\n"
                            f"- Issue Title: {issue_title}\n"
                            f"- Issue URL: {issue_url or '(local/manual)'}\n\n"
                            f"{triage.content}\n"
                        ),
                    )
                    repo.add_job_event(job_id, "triage", "completed", "Triage completed.")

                _run_stage("triage", triage_stage)
                _check_spend_caps(repo, settings, repo.get_job(job_id))
                repo.update_job_status(job, JobStatus.RUNNING, stage="plan")

                def plan_stage() -> None:
                    plan = llm.generate(
                        settings.model_build,
                        (
                            "Generate a concrete execution checklist and expected tests for this task.\n"
                            f"Repository: {job.repo}\nIssue: {job.issue_number}\nTitle: {issue_title}"
                        ),
                    )
                    repo.add_cost(job_id, plan.model, plan.prompt_tokens, plan.completion_tokens, plan.cost_usd)
                    JOB_COST.inc(plan.cost_usd)
                    existing = (artifact_dir / "plan.md").read_text(encoding="utf-8")
                    write_text(artifact_dir / "plan.md", existing + "\n## Execution Checklist\n" + plan.content + "\n")
                    repo.add_job_event(job_id, "plan", "completed", "Planning completed.")

                _run_stage("plan", plan_stage)
                _check_spend_caps(repo, settings, repo.get_job(job_id))
                repo.update_job_status(job, JobStatus.RUNNING, stage="execute")

                def execute_stage() -> None:
                    nonlocal changed_paths
                    if fast_mode:
                        changed_paths = ["README.md"]
                        patch = (
                            "--- a/README.md\n"
                            "+++ b/README.md\n"
                            "@@\n"
                            "+# Agent run summary\n"
                            "+Generated patch placeholder for draft PR context.\n"
                        )
                    else:
                        install_token = github.installation_token()
                        clone_source = GitHubAppClient.repo_https_url(job.repo)
                        code, output = _run_git_command(
                            ["clone", "--single-branch", "--branch", job.base_branch, clone_source, str(repo_workspace)],
                            timeout_seconds=300,
                            cwd=workspace_root,
                            auth_token=install_token,
                        )
                        if code != 0:
                            raise RuntimeError(f"GIT_CLONE_FAILED: {output.strip()}")

                        code, output = _run_git_command(
                            ["checkout", "-b", branch_name],
                            timeout_seconds=60,
                            cwd=repo_workspace,
                        )
                        if code != 0:
                            raise RuntimeError(f"GIT_CHECKOUT_FAILED: {output.strip()}")

                        issue_excerpt = issue_body[:2000] if issue_body else "(no issue body provided)"
                        change_note = llm.generate(
                            settings.model_build,
                            (
                                "Write concise markdown implementation notes for this coding task.\n"
                                "Use sections: Summary, Changes, Validation.\n"
                                f"Repository: {job.repo}\n"
                                f"Issue: #{job.issue_number}\n"
                                f"Title: {issue_title}\n"
                                f"Body:\n{issue_excerpt}"
                            ),
                            max_tokens=500,
                        )
                        repo.add_cost(
                            job_id,
                            change_note.model,
                            change_note.prompt_tokens,
                            change_note.completion_tokens,
                            change_note.cost_usd,
                        )
                        JOB_COST.inc(change_note.cost_usd)

                        rel_path = f"docs/agent-runs/{job_id}.md"
                        output_path = repo_workspace / rel_path
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        content = (
                            f"# Agent Draft for Issue #{job.issue_number}\n\n"
                            f"Original issue: {issue_url or '(not available)'}\n\n"
                            f"{change_note.content}\n"
                        )
                        if policy.secrets_detected(content):
                            raise RuntimeError("SECRET_PATTERN_DETECTED_IN_PATCH")
                        write_text(output_path, content)
                        changed_paths = [rel_path]

                        code, output = _run_git_command(
                            ["add", "-N", rel_path],
                            timeout_seconds=60,
                            cwd=repo_workspace,
                        )
                        if code != 0:
                            raise RuntimeError(f"GIT_ADD_INTENT_FAILED: {output.strip()}")

                        code, patch = _run_git_command(
                            ["diff", "--", rel_path],
                            timeout_seconds=60,
                            cwd=repo_workspace,
                        )
                        if code != 0:
                            raise RuntimeError(f"GIT_DIFF_FAILED: {patch.strip()}")
                        if not patch.strip():
                            raise RuntimeError("NO_PATCH_GENERATED")

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

                    write_text(artifact_dir / "patch.diff", patch)
                    repo.add_policy_audit(job_id, "allow", "allowed_paths", "Changed paths validated.")
                    repo.add_job_event(job_id, "execute", "completed", "Execution stage produced patch artifact.")

                _run_stage("execute", execute_stage)
                job = repo.get_job(job_id)
                if job and job.status == JobStatus.AWAITING_APPROVAL.value:
                    return

                repo.update_job_status(job, JobStatus.RUNNING, stage="test")

                def test_stage() -> None:
                    outputs: list[str] = []
                    execution_cwd = repo_workspace if repo_workspace.exists() else workspace_root
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
                            cwd=execution_cwd,
                            fast_mode=fast_mode,
                        )
                        outputs.append(f"$ {command}\n{output}\n")
                        if code != 0:
                            raise RuntimeError(f"ACCEPTANCE_COMMAND_FAILED: {command}")
                    write_text(artifact_dir / "test.log", "\n".join(outputs))
                    repo.add_job_event(job_id, "test", "completed", "Acceptance commands completed.")

                _run_stage("test", test_stage)
                repo.update_job_status(job, JobStatus.RUNNING, stage="review")

                def review_stage() -> None:
                    review = llm.generate(
                        settings.model_review,
                        (
                            "Write concise PR review notes emphasizing risk, tests, and rollback guidance.\n"
                            f"Issue: #{job.issue_number}\nTitle: {issue_title}\nChanged paths: {', '.join(changed_paths)}"
                        ),
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

                def pr_stage() -> None:
                    if fast_mode:
                        pr_url = None
                    else:
                        if not repo_workspace.exists():
                            raise RuntimeError("WORKSPACE_NOT_READY")

                        install_token = github.installation_token()
                        commands: list[list[str]] = [
                            ["config", "user.name", "codex-home[bot]"],
                            ["config", "user.email", "codex-home[bot]@users.noreply.github.com"],
                            ["add", "--all"],
                        ]
                        for command in commands:
                            code, output = _run_git_command(
                                command,
                                timeout_seconds=60,
                                cwd=repo_workspace,
                            )
                            if code != 0:
                                raise RuntimeError(f"GIT_COMMAND_FAILED ({' '.join(command)}): {output.strip()}")

                        code, status_output = _run_git_command(
                            ["status", "--porcelain"],
                            timeout_seconds=60,
                            cwd=repo_workspace,
                        )
                        if code != 0:
                            raise RuntimeError(f"GIT_STATUS_FAILED: {status_output.strip()}")
                        if not status_output.strip():
                            raise RuntimeError("NO_CHANGES_TO_COMMIT")

                        commit_message = f"chore(agent): address issue #{job.issue_number}"
                        code, output = _run_git_command(
                            ["commit", "-m", commit_message],
                            timeout_seconds=90,
                            cwd=repo_workspace,
                        )
                        if code != 0:
                            raise RuntimeError(f"GIT_COMMIT_FAILED: {output.strip()}")

                        code, output = _run_git_command(
                            ["push", "-u", "origin", branch_name],
                            timeout_seconds=180,
                            cwd=repo_workspace,
                            auth_token=install_token,
                        )
                        if code != 0:
                            raise RuntimeError(f"GIT_PUSH_FAILED: {output.strip()}")

                        review_text = (artifact_dir / "review.md").read_text(encoding="utf-8").strip()
                        pr_body = (
                            f"Automated draft PR for issue #{job.issue_number}.\n\n"
                            f"Issue: {issue_url or f'#{job.issue_number}'}\n\n"
                            f"## Review Notes\n{review_text}\n"
                        )
                        pr_url = github.create_draft_pull_request(
                            repo=job.repo,
                            title=f"[agent] {issue_title}"[:120],
                            head=branch_name,
                            base=job.base_branch,
                            body=pr_body,
                        )

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
                    message = "Fast mode completed (no PR created)." if fast_mode else "Draft PR prepared."
                    repo.add_job_event(job_id, "pr", "completed", message)
                    repo.update_job_status(job, JobStatus.COMPLETED, stage="pr", pr_url=pr_url)

                _run_stage("pr", pr_stage)
                JOBS_COMPLETED.labels(status=JobStatus.COMPLETED.value).inc()
                append_jsonl(run_log, {"ts": _utc_now().isoformat(), "event": "job_completed"})

        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            logger.exception("Job failed", extra={"job_id": job_id})
            latest_job = repo.get_job(job_id)
            if latest_job and latest_job.status == JobStatus.AWAITING_APPROVAL.value:
                append_jsonl(run_log, {"ts": _utc_now().isoformat(), "event": "job_waiting_approval"})
                return
            if latest_job:
                repo.update_job_status(latest_job, JobStatus.FAILED, stage=latest_job.current_stage, reason=message)
                repo.add_job_event(job_id, latest_job.current_stage or "unknown", "failed", message)
                JOBS_COMPLETED.labels(status=JobStatus.FAILED.value).inc()
            append_jsonl(run_log, {"ts": _utc_now().isoformat(), "event": "job_failed", "error": message})
