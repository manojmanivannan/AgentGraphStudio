## What to build

Wire the durable run model into the development and deployment story and prove the full resilience path end to end. The backend and worker should be able to run together in development, and the full system should survive tab closes, reconnects, stop actions, and worker restarts.

## Acceptance criteria

- [ ] The backend can run with a separate execution worker in development and production-like setups.
- [ ] End-to-end tests cover start, disconnect, reconnect, completion, and abort flows.
- [ ] The chat UI reflects completed and aborted terminal states correctly after reconnect.
- [ ] The architecture docs explain the new ownership model and replay semantics.

## Blocked by

- [002-background-worker-owns-execution.md](002-background-worker-owns-execution.md)
- [003-live-replay-for-reconnecting-clients.md](003-live-replay-for-reconnecting-clients.md)
- [004-stop-button-aborts-running-execution.md](004-stop-button-aborts-running-execution.md)
- [005-hitl-and-approval-resume-after-reconnect.md](005-hitl-and-approval-resume-after-reconnect.md)