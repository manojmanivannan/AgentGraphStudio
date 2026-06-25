## What to build

Make human-in-the-loop input and tool approval survive disconnects by persisting pending interrupt state and allowing responses to be submitted after reconnect. The prompt or approval request should be addressable by persisted run/request identifiers, not by a live socket session.

## Acceptance criteria

- [ ] HITL and tool approval requests are stored durably with identifiers that can be resumed later.
- [ ] A user can reconnect and answer a pending interrupt without restarting the run.
- [ ] The worker resumes cleanly after the interrupt is resolved.
- [ ] Backend and frontend tests cover disconnect-then-respond flows.

## Blocked by

- [001-durable-run-state-foundation.md](001-durable-run-state-foundation.md)
- [002-background-worker-owns-execution.md](002-background-worker-owns-execution.md)
- [003-live-replay-for-reconnecting-clients.md](003-live-replay-for-reconnecting-clients.md)