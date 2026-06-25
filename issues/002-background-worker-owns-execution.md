## What to build

Move agent execution off the WebSocket request lifecycle and into a backend-owned worker that claims durable runs, drives the existing runner to completion, and releases the browser from being the execution owner. Closing the tab should only drop the subscriber connection; the run continues until it completes, fails, or is aborted.

## Acceptance criteria

- [x] The backend can claim one runnable execution at a time and prevent duplicate ownership.
- [x] A worker can continue a run even if the original WebSocket disconnects.
- [x] A stale claim can be recovered after timeout or worker restart.
- [x] Route tests prove a disconnect does not cancel the underlying run.

## Blocked by

- [001-durable-run-state-foundation.md](001-durable-run-state-foundation.md)