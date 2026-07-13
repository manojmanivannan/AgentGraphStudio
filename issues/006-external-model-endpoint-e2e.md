## Parent PRD

`.scratch/prd-self-contained-linux-runtime.md`

## What to build

Implement end-to-end external model endpoint usage in the self-contained runtime so inference is functional with user-provided providers and defaults remain lightweight.

## Acceptance criteria

- [ ] Configured external endpoint is used for agent inference end-to-end.
- [ ] Misconfiguration paths provide actionable runtime diagnostics.
- [ ] Default runtime remains operable without bundling local model runtimes.

## Blocked by

- Blocked by `issues/005-runtime-config-surface-defaults-profile.md`

## User stories addressed

- User story 17
- User story 18
