## What to build

Make the chat stop button produce an explicit aborted terminal state in the backend. The stop action should persist a cancellation request, the worker should observe it cooperatively, and the run should end as aborted rather than just losing the socket connection.

## Acceptance criteria

- [x] Pressing stop marks the active run as aborting in persistent state.
- [x] The worker stops the run at a safe cancellation boundary and records the final state as aborted.
- [x] Aborted runs do not resume automatically on reconnect.
- [x] Tests cover stop during an active run, disconnect, and the final aborted state.

## Blocked by

- [001-durable-run-state-foundation.md](001-durable-run-state-foundation.md)
- [002-background-worker-owns-execution.md](002-background-worker-owns-execution.md)