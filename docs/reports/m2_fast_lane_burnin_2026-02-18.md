# Milestone 2 Burn-In Report (Fast Lane)

Date (UTC): `2026-02-18`
Mode: `RUN_MODE=fast`
Scope: `SydFloyd/KaolCode`

## Objective

Validate milestone 2 exit criteria:

- 20/20 fast jobs complete.
- No unsafe events.

## Run Summary

- Total jobs: `20`
- Finalized jobs: `20`
- Completed: `20`
- Failed: `0`
- Rejected: `0`
- Awaiting approval: `0`
- Mean duration: `3.967s`
- p95 duration: `7.056s`
- Total reported cost: `$0.003480`

## Inputs

- API: `POST /api/v1/jobs`
- `risk_class=code`
- `model_profile=build`
- `created_by=burnin-m2`
- Issue numbers: `620001..620020`

## Representative Output

- First job: `ee15ae7c-488e-4c92-b2de-affdcb0c43d5`
- Last job: `31709280-e8ae-4910-9d31-4707fbb60106`
- All jobs finished in stage `pr` with status `completed`.

## Conclusion

Milestone 2 burn-in gate passed for fast-lane reliability on this environment.
