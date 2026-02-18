from pathlib import Path

from fastapi.testclient import TestClient

from codex_home.config import Settings
from codex_home.github_api import GitHubIssue
from codex_home.orchestrator import create_app


def _write_test_policy(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "version: 1",
                "repo_allowlist:",
                "  - acme/repo",
                "sensitive_paths:",
                "  - infra/**",
                "blocked_commands:",
                "  exact: []",
                "  regex: []",
                "domain_allowlist:",
                "  - api.github.com",
                "default_caps:",
                "  max_minutes: 45",
                "  max_iterations: 8",
                "  max_usd: 3.0",
                "max_parallel_jobs: 2",
                "max_usd_per_day: 40",
                "max_usd_per_month: 900",
                "approval_matrix:",
                "  code: [\"merge\"]",
                "  deps: [\"merge\"]",
                "  infra: [\"infra\", \"merge\"]",
                "  secrets: [\"secrets\", \"merge\"]",
                "  destructive: [\"destructive\", \"merge\"]",
                "secret_patterns: []",
            ]
        ),
        encoding="utf-8",
    )


def _write_test_repos(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "repos:",
                "  - name: acme/repo",
                "    enabled: true",
                "    base_branch: main",
                "    allowed_paths:",
                "      - src/**",
                "      - tests/**",
                "    acceptance_commands:",
                "      - pytest -q",
            ]
        ),
        encoding="utf-8",
    )


def _build_settings(tmp_path: Path, run_mode: str = "fast") -> Settings:
    policy_path = tmp_path / "policy.yaml"
    repos_path = tmp_path / "repos.yaml"
    db_path = tmp_path / "test.db"
    _write_test_policy(policy_path)
    _write_test_repos(repos_path)
    return Settings.model_validate(
        {
            "APP_ENV": "test",
            "LOG_LEVEL": "INFO",
            "DATABASE_URL": f"sqlite+pysqlite:///{db_path}",
            "REDIS_URL": "redis://localhost:6399/0",
            "QUEUE_NAME": "jobs",
            "WEBHOOK_SECRET": "",
            "OPERATOR_TOKEN": "test-token",
            "POLICY_PATH": str(policy_path),
            "REPOS_PATH": str(repos_path),
            "ARTIFACT_ROOT": str(tmp_path / "artifacts"),
            "AUTO_MIGRATE": True,
            "DISABLE_QUEUE": True,
            "RUN_MODE": run_mode,
        }
    )


def test_create_and_fetch_job(tmp_path: Path):
    app = create_app(_build_settings(tmp_path))
    client = TestClient(app)
    headers = {"X-Operator-Token": "test-token"}

    create_payload = {
        "repo": "acme/repo",
        "issue_number": 42,
        "base_branch": "main",
        "risk_class": "code",
        "model_profile": "build",
        "created_by": "tester",
    }
    create_resp = client.post("/api/v1/jobs", json=create_payload, headers=headers)
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["status"] == "queued"

    job_id = created["job_id"]
    get_resp = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert get_resp.status_code == 200
    payload = get_resp.json()
    assert payload["job"]["repo"] == "acme/repo"
    assert len(payload["events"]) >= 1


def test_control_endpoints_require_token(tmp_path: Path):
    app = create_app(_build_settings(tmp_path))
    client = TestClient(app)

    denied = client.post("/api/v1/control/kill-switch")
    assert denied.status_code == 403

    allowed = client.post("/api/v1/control/kill-switch", headers={"X-Operator-Token": "test-token"})
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "disabled"


def test_intake_text_fast_mode_queues_without_github(tmp_path: Path):
    app = create_app(_build_settings(tmp_path, run_mode="fast"))
    client = TestClient(app)
    headers = {"X-Operator-Token": "test-token"}

    payload = {
        "repo": "acme/repo",
        "title": "Tighten policy docs",
        "body": "Refresh quickstart examples.",
        "labels": ["docs"],
        "risk_class": "code",
        "model_profile": "build",
        "created_by": "tester",
    }

    response = client.post("/api/v1/intake/text", json=payload, headers=headers)
    assert response.status_code == 200
    created = response.json()
    assert created["status"] == "queued"
    assert int(created["issue_number"]) >= 1


def test_intake_text_release_mode_creates_github_issue(tmp_path: Path, monkeypatch):
    from codex_home import orchestrator as orch_module

    def fake_create_issue(self, repo: str, title: str, body: str, labels: list[str]) -> GitHubIssue:  # noqa: ARG001
        return GitHubIssue(number=777, title=title, body=body, html_url="https://example.invalid/issues/777")

    monkeypatch.setattr(orch_module.GitHubAppClient, "create_issue", fake_create_issue)

    app = create_app(_build_settings(tmp_path, run_mode="release"))
    client = TestClient(app)
    headers = {"X-Operator-Token": "test-token"}
    payload = {
        "repo": "acme/repo",
        "title": "Create issue in release mode",
        "body": "Should use GitHub issue number.",
        "labels": ["docs"],
        "risk_class": "code",
        "model_profile": "build",
        "created_by": "tester",
    }

    response = client.post("/api/v1/intake/text", json=payload, headers=headers)
    assert response.status_code == 200
    created = response.json()
    assert created["status"] == "queued"
    assert created["issue_number"] == 777
