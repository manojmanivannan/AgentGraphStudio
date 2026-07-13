## Parent PRD

`.scratch/prd-self-contained-linux-runtime.md`

## What to build

Deliver parity for core canvas graph semantics in the self-contained runtime so Worker/Router execution, Agent Node and Tool Node loading, and Edge/Handoff behavior remain consistent with existing contracts.

## Acceptance criteria

- [ ] Worker and Router execution behavior remains consistent for existing workflows.
- [ ] Agent Node and Tool Node definitions load without compatibility regressions.
- [ ] Edge and handoff semantics remain stable and verifiable in integration tests.

## Blocked by

- Blocked by `issues/003-user-data-dirs-bundled-postgres-boot.md`
- Blocked by `issues/004-mandatory-kvm-isolation-failure-ux.md`
- Blocked by `issues/005-runtime-config-surface-defaults-profile.md`

## User stories addressed

- User story 6
- User story 7
- User story 8
- User story 23
- User story 35
