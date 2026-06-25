## What to build

Create the durable execution foundation for conversation runs so the backend owns run lifecycle instead of the browser tab. The run should have persisted state for status, prompt, target agent, attempt count, ownership/lease metadata, timestamps, and replay position. The existing conversation messages remain the user-facing history, but run state becomes the control-plane source of truth.

## Acceptance criteria

- [x] A run record can be created for a conversation and resumed by the backend.
- [x] The run record persists status and ownership metadata needed for later claim/replay behavior.
- [x] Execution events can be stored in sequence order for replay after reconnect.
- [x] Backend tests prove run creation, replay ordering, and terminal state transitions.

## Blocked by

None - can start immediately