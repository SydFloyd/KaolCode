from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml

from codex_home.types import ApprovalAction, Caps, RiskClass


@dataclass
class BlockedCommands:
    exact: list[str]
    regex: list[str]


@dataclass
class PolicyProfile:
    repo_allowlist: list[str]
    sensitive_paths: list[str]
    blocked_commands: BlockedCommands
    domain_allowlist: list[str]
    default_caps: Caps
    max_parallel_jobs: int
    max_usd_per_day: float
    max_usd_per_month: float
    approval_matrix: dict[RiskClass, list[ApprovalAction]]
    secret_patterns: list[str]

    def repo_allowed(self, repo: str) -> bool:
        return repo in self.repo_allowlist

    def is_blocked_command(self, command: str) -> bool:
        normalized = command.strip()
        if normalized in self.blocked_commands.exact:
            return True
        return any(re.search(pattern, normalized) for pattern in self.blocked_commands.regex)

    def requires_sensitive_approval(self, changed_paths: list[str]) -> bool:
        for changed in changed_paths:
            if any(fnmatch.fnmatch(changed, pat) for pat in self.sensitive_paths):
                return True
        return False

    def allowed_path_violation(self, changed_paths: list[str], allowed_paths: list[str]) -> list[str]:
        violations: list[str] = []
        for changed in changed_paths:
            if not any(fnmatch.fnmatch(changed, pat) for pat in allowed_paths):
                violations.append(changed)
        return violations

    def secrets_detected(self, content: str) -> bool:
        return any(re.search(pattern, content) for pattern in self.secret_patterns)

    def domain_allowed(self, url: str) -> bool:
        host = urlparse(url).hostname
        if not host:
            return False
        return any(host == allowed or host.endswith(f".{allowed}") for allowed in self.domain_allowlist)

    def required_approvals(self, risk_class: RiskClass) -> list[ApprovalAction]:
        return self.approval_matrix.get(risk_class, [ApprovalAction.MERGE])


def _load_yaml(path: str) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_policy(path: str) -> PolicyProfile:
    raw = _load_yaml(path)
    matrix_raw = raw.get("approval_matrix", {})
    approval_matrix: dict[RiskClass, list[ApprovalAction]] = {}
    for key, values in matrix_raw.items():
        approval_matrix[RiskClass(key)] = [ApprovalAction(value) for value in values]

    return PolicyProfile(
        repo_allowlist=list(raw.get("repo_allowlist", [])),
        sensitive_paths=list(raw.get("sensitive_paths", [])),
        blocked_commands=BlockedCommands(
            exact=list(raw.get("blocked_commands", {}).get("exact", [])),
            regex=list(raw.get("blocked_commands", {}).get("regex", [])),
        ),
        domain_allowlist=list(raw.get("domain_allowlist", [])),
        default_caps=Caps.model_validate(raw.get("default_caps", {})),
        max_parallel_jobs=int(raw.get("max_parallel_jobs", 1)),
        max_usd_per_day=float(raw.get("max_usd_per_day", 40.0)),
        max_usd_per_month=float(raw.get("max_usd_per_month", 900.0)),
        approval_matrix=approval_matrix,
        secret_patterns=list(raw.get("secret_patterns", [])),
    )


def load_repo_profiles(path: str) -> dict[str, dict]:
    raw = _load_yaml(path)
    profiles: dict[str, dict] = {}
    for entry in raw.get("repos", []):
        name = entry["name"]
        profiles[name] = {
            "enabled": bool(entry.get("enabled", True)),
            "base_branch": entry.get("base_branch", "main"),
            "allowed_paths": list(entry.get("allowed_paths", [])),
            "acceptance_commands": list(entry.get("acceptance_commands", [])),
        }
    return profiles

