## Parent PRD

`.scratch/prd-self-contained-linux-runtime.md`

## What to build

Add an app-owned supervisor lifecycle that starts required services, monitors them, and performs deterministic shutdown on normal exit, interrupt, or failure. Recovery behavior should be clean and observable after abnormal termination.

## Acceptance criteria

- [ ] Supervisor starts/stops managed services in a deterministic order.
- [ ] App exit guarantees managed child process cleanup with no orphan processes.
- [ ] Lifecycle logs include start, stop, restart, and failure transitions for support triage.

## Blocked by

- Blocked by `issues/001-runtime-launch-contract-preflight-diagnostics.md`

## User stories addressed

- User story 14
- User story 15
- User story 28
