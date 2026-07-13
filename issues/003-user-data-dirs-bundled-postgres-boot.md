## Parent PRD

`.scratch/prd-self-contained-linux-runtime.md`

## What to build

Implement per-user runtime data/config/cache directories and boot a bundled local PostgreSQL process under supervisor control. User data persists across launches and does not require root privileges during normal operation.

## Acceptance criteria

- [ ] Runtime uses deterministic per-user directories for data/config/cache.
- [ ] Bundled PostgreSQL initializes and runs as a managed local process.
- [ ] Canvas and conversation persistence survives app restart and crash recovery scenarios.

## Blocked by

- Blocked by `issues/001-runtime-launch-contract-preflight-diagnostics.md`
- Blocked by `issues/002-supervisor-lifecycle-deterministic-shutdown.md`

## User stories addressed

- User story 4
- User story 5
- User story 15
