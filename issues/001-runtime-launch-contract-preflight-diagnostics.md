## Parent PRD

`.scratch/prd-self-contained-linux-runtime.md`

## What to build

Implement a black-box runtime launch contract for the self-contained app with startup preflight checks and clear diagnostics. A user can launch the app artifact, see pass/fail checks before services start, and receive actionable capability/dependency error classes.

## Acceptance criteria

- [ ] Launch entrypoint performs preflight checks before starting internal services.
- [ ] Preflight results are surfaced to users with actionable messages and distinct failure classes.
- [ ] Runtime health checks are executed at launch and reported in logs/diagnostics output.

## Blocked by

None - can start immediately.

## User stories addressed

- User story 1
- User story 2
- User story 25
- User story 32
- User story 34
