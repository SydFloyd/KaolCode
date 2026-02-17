from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import jwt

from codex_home.config import Settings


API_ROOT = "https://api.github.com"


def _parse_utc_timestamp(value: str) -> float:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).timestamp()


@dataclass
class GitHubIssue:
    number: int
    title: str
    body: str
    html_url: str


class GitHubAppClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._installation_token: str = ""
        self._installation_token_expiry: float = 0.0

    def _assert_configured(self) -> None:
        missing: list[str] = []
        if not self.settings.github_app_id:
            missing.append("GITHUB_APP_ID")
        if not self.settings.github_app_installation_id:
            missing.append("GITHUB_APP_INSTALLATION_ID")
        if not self.settings.github_app_private_key_pem:
            missing.append("GITHUB_APP_PRIVATE_KEY_PEM")
        if missing:
            raise RuntimeError(f"GITHUB_APP_CONFIG_MISSING: {', '.join(missing)}")

    def _private_key(self) -> str:
        pem = self.settings.github_app_private_key_pem.strip()
        if "\\n" in pem:
            pem = pem.replace("\\n", "\n")
        if not pem.endswith("\n"):
            pem += "\n"
        return pem

    def _app_jwt(self) -> str:
        self._assert_configured()
        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + 540,
            "iss": self.settings.github_app_id,
        }
        token = jwt.encode(payload, self._private_key(), algorithm="RS256")
        if isinstance(token, bytes):
            return token.decode("utf-8")
        return token

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "codex-home/0.1.0",
        }

    @staticmethod
    def split_repo(repo: str) -> tuple[str, str]:
        if "/" not in repo:
            raise RuntimeError(f"INVALID_REPO_SLUG: {repo}")
        owner, name = repo.split("/", 1)
        if not owner or not name:
            raise RuntimeError(f"INVALID_REPO_SLUG: {repo}")
        return owner, name

    @staticmethod
    def repo_https_url(repo: str) -> str:
        owner, name = GitHubAppClient.split_repo(repo)
        return f"https://github.com/{owner}/{name}.git"

    def installation_token(self) -> str:
        now = time.time()
        if self._installation_token and now < (self._installation_token_expiry - 60):
            return self._installation_token

        app_token = self._app_jwt()
        url = f"{API_ROOT}/app/installations/{self.settings.github_app_installation_id}/access_tokens"
        with httpx.Client(timeout=20.0) as client:
            response = client.post(url, headers=self._headers(app_token))
        if response.status_code != 201:
            raise RuntimeError(f"GITHUB_INSTALLATION_TOKEN_FAILED: {response.status_code} {response.text}")

        payload = response.json()
        token = payload.get("token", "")
        expires_at = payload.get("expires_at", "")
        if not token or not expires_at:
            raise RuntimeError("GITHUB_INSTALLATION_TOKEN_INVALID_RESPONSE")

        self._installation_token = token
        self._installation_token_expiry = _parse_utc_timestamp(expires_at)
        return token

    def get_issue(self, repo: str, issue_number: int) -> GitHubIssue:
        token = self.installation_token()
        owner, name = self.split_repo(repo)
        url = f"{API_ROOT}/repos/{owner}/{name}/issues/{issue_number}"
        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, headers=self._headers(token))
        if response.status_code != 200:
            raise RuntimeError(f"GITHUB_GET_ISSUE_FAILED: {response.status_code} {response.text}")
        payload = response.json()
        return GitHubIssue(
            number=int(payload.get("number", issue_number)),
            title=str(payload.get("title", "")),
            body=str(payload.get("body", "") or ""),
            html_url=str(payload.get("html_url", "")),
        )

    def create_issue(self, repo: str, title: str, body: str, labels: list[str]) -> GitHubIssue:
        token = self.installation_token()
        owner, name = self.split_repo(repo)
        url = f"{API_ROOT}/repos/{owner}/{name}/issues"
        payload = {"title": title, "body": body, "labels": labels}
        with httpx.Client(timeout=20.0) as client:
            response = client.post(url, headers=self._headers(token), json=payload)
        if response.status_code != 201:
            raise RuntimeError(f"GITHUB_CREATE_ISSUE_FAILED: {response.status_code} {response.text}")
        data = response.json()
        return GitHubIssue(
            number=int(data["number"]),
            title=str(data.get("title", "")),
            body=str(data.get("body", "") or ""),
            html_url=str(data.get("html_url", "")),
        )

    def create_draft_pull_request(
        self,
        repo: str,
        title: str,
        head: str,
        base: str,
        body: str,
    ) -> str:
        token = self.installation_token()
        owner, name = self.split_repo(repo)
        url = f"{API_ROOT}/repos/{owner}/{name}/pulls"
        payload = {
            "title": title,
            "head": head,
            "base": base,
            "body": body,
            "draft": True,
        }
        with httpx.Client(timeout=20.0) as client:
            response = client.post(url, headers=self._headers(token), json=payload)
        if response.status_code != 201:
            raise RuntimeError(f"GITHUB_CREATE_PR_FAILED: {response.status_code} {response.text}")
        return str(response.json().get("html_url", ""))
