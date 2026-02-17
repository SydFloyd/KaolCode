from codex_home.policy import load_policy


def test_blocked_command_detection():
    policy = load_policy("config/policy.yaml")
    assert policy.is_blocked_command("rm -rf /")
    assert policy.is_blocked_command("terraform destroy -auto-approve")
    assert not policy.is_blocked_command("pytest -q")


def test_allowed_path_violation():
    policy = load_policy("config/policy.yaml")
    violations = policy.allowed_path_violation(
        changed_paths=["src/app.py", "infra/main.tf"],
        allowed_paths=["src/**", "tests/**"],
    )
    assert "infra/main.tf" in violations
    assert "src/app.py" not in violations


def test_domain_allowlist():
    policy = load_policy("config/policy.yaml")
    assert policy.domain_allowed("https://api.github.com/repos/example/project")
    assert not policy.domain_allowed("https://malicious.example.net/path")

