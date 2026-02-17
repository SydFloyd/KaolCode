# Pilot Projects (First 8 Weeks)

## 1) Dependency Upgrade + Vulnerability Fix PRs

- Intake labels: `agent-ready`, `deps`, `security`
- Output: minimal dependency bump, changelog summary, passing tests, `sbom.json` when applicable
- KPI: reduce high/critical advisories by 50% on pilot repos

## 2) CI Red-to-Green Fixer

- Intake: failing workflow issues and pipeline failures
- Output: deterministic fix PR + regression test + root-cause note in `review.md`
- KPI: recurring CI failures reduced by 30%

## 3) Test Reliability / Flake Reduction

- Intake: flaky test tickets and intermittent failure patterns
- Output: deterministic test fix or quarantine PR + follow-up issue link
- KPI: flaky incidents reduced by 40%
