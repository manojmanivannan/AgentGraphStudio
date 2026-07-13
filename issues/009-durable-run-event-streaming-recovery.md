## Parent PRD

`.scratch/prd-self-contained-linux-runtime.md`

## What to build

Preserve durable run and execution event streaming behavior under transient UI disconnects so long-running conversations continue and replay/stream semantics remain intuitive.

## Acceptance criteria

- [ ] Runs continue when websocket/UI disconnects occur.
- [ ] Reconnect resumes/replays event stream without losing conversation continuity.
- [ ] Stop/cancel behavior remains consistent with current user-facing semantics.

## Blocked by

- Blocked by `issues/008-canvas-graph-semantics-parity.md`

## User stories addressed

- User story 11
- User story 12
- User story 24
