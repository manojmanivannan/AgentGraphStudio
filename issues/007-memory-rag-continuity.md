## Parent PRD

`.scratch/prd-self-contained-linux-runtime.md`

## What to build

Preserve Memory and RAG Documents continuity in the self-contained runtime so existing behavior remains available with local persistence and expected retrieval outcomes.

## Acceptance criteria

- [ ] Memory tools continue to store and retrieve context across runs.
- [ ] RAG document ingest and retrieval behavior remains available in runtime workflows.
- [ ] Regression tests confirm no behavior drift versus current contract expectations.

## Blocked by

- Blocked by `issues/003-user-data-dirs-bundled-postgres-boot.md`
- Blocked by `issues/005-runtime-config-surface-defaults-profile.md`

## User stories addressed

- User story 9
- User story 10
