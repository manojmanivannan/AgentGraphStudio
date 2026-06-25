## What to build

Make the UI a replayable subscriber to execution rather than a one-shot live stream. When the client reconnects, it should ask for missed execution events from the backend and rebuild the current turn state from persisted data before resuming live updates.

## Acceptance criteria

- [x] The backend can return execution events after a given sequence number or cursor.
- [x] The chat UI can reconnect and continue rendering the current run without losing prior steps.
- [x] Replayed events produce the same visible message grouping as live events.
- [x] Frontend tests cover disconnect, reconnect, and recovery of missed events.

## Blocked by

- [001-durable-run-state-foundation.md](001-durable-run-state-foundation.md)