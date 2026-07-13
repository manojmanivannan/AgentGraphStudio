## Parent PRD

`.scratch/prd-self-contained-linux-runtime.md`

## What to build

Provide runtime configuration surface and defaults profile for self-contained execution, including external inference endpoint configuration and MLflow optional mode disabled by default.

## Acceptance criteria

- [ ] Runtime exposes user-level configuration for external model endpoint settings.
- [ ] Default configuration does not require bundled local model weights.
- [ ] MLflow observability remains disabled unless explicitly enabled.

## Blocked by

- Blocked by `issues/001-runtime-launch-contract-preflight-diagnostics.md`
- Blocked by `issues/002-supervisor-lifecycle-deterministic-shutdown.md`

## User stories addressed

- User story 17
- User story 18
- User story 19
- User story 20
