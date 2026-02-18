from __future__ import annotations


def normalize_failure_code(reason: str | None) -> str:
    if not reason:
        return "UNKNOWN"
    raw = reason.strip()
    if not raw:
        return "UNKNOWN"
    return raw.split(":", 1)[0].strip().upper()


def classify_failure_reason(reason: str | None) -> str:
    code = normalize_failure_code(reason)

    if code.startswith("CAP_"):
        return "budget_cap"
    if code.startswith("BLOCKED_COMMAND"):
        return "command_policy"
    if code.startswith("DOMAIN_NOT_ALLOWLISTED"):
        return "domain_policy"
    if code.startswith("ALLOWED_PATHS_VIOLATION"):
        return "path_policy"
    if code.endswith("APPROVAL_REQUIRED"):
        return "approval_gate"
    if code.startswith("SECRET_PATTERN_DETECTED"):
        return "secret_guard"
    if code.startswith("ACCEPTANCE_COMMAND_FAILED"):
        return "acceptance_test"
    if code.startswith("GIT_"):
        return "git_failure"
    if code.startswith("GITHUB_"):
        return "github_api"
    if code.startswith("KILL_SWITCH_ACTIVE"):
        return "safety_control"
    if code.startswith("NO_"):
        return "execution_logic"
    if code.startswith("WORKSPACE_NOT_READY"):
        return "runtime_state"
    if code.startswith("INVALID_"):
        return "input_validation"
    return "runtime_error"
