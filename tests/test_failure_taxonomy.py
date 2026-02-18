from codex_home.failure_taxonomy import classify_failure_reason, normalize_failure_code


def test_normalize_failure_code():
    assert normalize_failure_code("CAP_COST_EXCEEDED: over limit") == "CAP_COST_EXCEEDED"
    assert normalize_failure_code("  blocked_command: rm -rf /  ") == "BLOCKED_COMMAND"
    assert normalize_failure_code("") == "UNKNOWN"
    assert normalize_failure_code(None) == "UNKNOWN"


def test_classify_failure_reason():
    assert classify_failure_reason("CAP_DAILY_BUDGET_EXCEEDED") == "budget_cap"
    assert classify_failure_reason("BLOCKED_COMMAND: rm -rf /") == "command_policy"
    assert classify_failure_reason("DOMAIN_NOT_ALLOWLISTED: example.org") == "domain_policy"
    assert classify_failure_reason("ALLOWED_PATHS_VIOLATION") == "path_policy"
    assert classify_failure_reason("SENSITIVE_PATH_APPROVAL_REQUIRED") == "approval_gate"
    assert classify_failure_reason("SECRET_PATTERN_DETECTED_IN_REVIEW") == "secret_guard"
    assert classify_failure_reason("ACCEPTANCE_COMMAND_FAILED: pytest -q") == "acceptance_test"
    assert classify_failure_reason("GIT_CLONE_FAILED: auth") == "git_failure"
    assert classify_failure_reason("GITHUB_CREATE_PR_FAILED: 403") == "github_api"
    assert classify_failure_reason("KILL_SWITCH_ACTIVE") == "safety_control"
    assert classify_failure_reason("NO_PATCH_GENERATED") == "execution_logic"
    assert classify_failure_reason("unhandled crash in worker") == "runtime_error"
