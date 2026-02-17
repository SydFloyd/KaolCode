# GitHub App Permissions Baseline

## Repository permissions

- Issues: Read and write
- Pull requests: Read and write
- Contents: Read and write
- Commit statuses: Read and write
- Checks: Read and write
- Metadata: Read-only

## Organization permissions

- None required for v1

## Webhook events

- Issues
- Issue comments (optional for future command interface)
- Pull request
- Pull request review

## Additional controls

- Install app only on allowlisted owned repos.
- Require branch protection on `main`.
- Disable direct pushes to protected branches.
- Require human review for all merges.
