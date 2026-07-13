## Parent PRD

`.scratch/prd-self-contained-linux-runtime.md`

## What to build

Create reproducible CI packaging for Linux AppImage with deterministic artifact generation and rollback-safe release metadata for shipping the self-contained runtime.

## Acceptance criteria

- [ ] CI builds AppImage artifacts reproducibly from tagged/revisioned inputs.
- [ ] Artifacts include version/build metadata needed for support and rollback.
- [ ] Packaging smoke checks validate first-run and restart viability.

## Blocked by

- Blocked by `issues/003-user-data-dirs-bundled-postgres-boot.md`
- Blocked by `issues/004-mandatory-kvm-isolation-failure-ux.md`
- Blocked by `issues/005-runtime-config-surface-defaults-profile.md`
- Blocked by `issues/008-canvas-graph-semantics-parity.md`

## User stories addressed

- User story 1
- User story 21
- User story 29
- User story 33
