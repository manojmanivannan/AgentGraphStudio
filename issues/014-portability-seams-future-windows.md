## Parent PRD

`.scratch/prd-self-contained-linux-runtime.md`

## What to build

Establish runtime contracts and abstraction seams that preserve future optional Windows support without forcing architectural rewrites after Linux-first delivery.

## Acceptance criteria

- [ ] Process, path, and capability abstractions isolate Linux-specific details behind contracts.
- [ ] Cross-platform constraints and assumptions are documented with validation checks.
- [ ] Linux-first implementation remains compatible with a future non-Linux adapter path.

## Blocked by

- Blocked by `issues/002-supervisor-lifecycle-deterministic-shutdown.md`
- Blocked by `issues/005-runtime-config-surface-defaults-profile.md`
- Blocked by `issues/011-appimage-build-reproducible-ci-artifact.md`

## User stories addressed

- User story 30
