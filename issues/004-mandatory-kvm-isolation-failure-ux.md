## Parent PRD

`.scratch/prd-self-contained-linux-runtime.md`

## What to build

Enforce strong tool execution isolation with mandatory KVM capability checks and user-facing failure UX when unavailable. Tool execution must not proceed in an insecure fallback mode.

## Acceptance criteria

- [ ] Runtime blocks tool execution when KVM capability is missing.
- [ ] User-facing diagnostics clearly explain why secure execution cannot start.
- [ ] Sandbox boundary behavior is documented and covered by capability/isolation tests.

## Blocked by

- Blocked by `issues/001-runtime-launch-contract-preflight-diagnostics.md`

## User stories addressed

- User story 3
- User story 13
- User story 31
