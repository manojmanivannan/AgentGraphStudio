# ADR 0007: WebSocket Execution Auth + Ownership Re-check

## Status

Accepted

## Context

Issue #31's auth map left one route open: the WebSocket run route
`/ws/conversations/{conversation_id}/run`. The route accepts a WS upgrade,
reads a prompt, and starts (or replays) an execution run against any
conversation id. Issue #36 added `Depends(get_current_user)` and an ownership
check to this route alongside the sibling REST execute routes, but:

1. The WS auth was never actually exercised. The existing WS tests
   (`test_routes_execute.py`) override `get_current_user` with a fake and stub
   the repos, so the real dependency never ran on the WS path; the REST-only
   isolation tests (`test_routes_execute_auth.py`) don't touch the socket. So
   the route remained effectively unauthenticated in practice.

2. The underlying reason it didn't work: `get_current_user` was declared
   `request: Request`. FastAPI only injects a `Request`-typed parameter for
   HTTP scopes — in `solve_dependencies` the request-param branch is gated on
   `isinstance(request, Request)`, which is `False` on a WebSocket route (the
   connection is a `WebSocket`). So on the WS path the `request` argument was
   never supplied and the dependency raised `TypeError: get_current_user()
   missing 1 required positional argument: 'request'` — which presents as a
   rejected upgrade, not as authentication.

The map also left an open decision: should ownership be re-checked **per run**
(each kick/queued run) or is **per-handshake** sufficient?

## Decision

1. **One auth dependency for HTTP and WS.** Type the connection parameter of
   `get_current_user` as `HTTPConnection` (the shared base of `Request` and
   `WebSocket`) instead of `Request`. FastAPI injects an `HTTPConnection`-
   typed parameter unconditionally for both scopes, and `HTTPConnection`
   exposes `.cookies`, so the same dependency authenticates REST routes and
   the WS run route. No separate WS-specific auth path.

2. **Handshake auth + per-handshake ownership check.** Authentication happens
   at the upgrade via `Depends(get_current_user)` (FastAPI rejects the upgrade
   before `accept()` when it raises `HTTPException`). Ownership of the path
   conversation is then verified once per connection, **before the prompt is
   read**, so a cross-user connection is rejected immediately with an error
   event and no run is created. No per-run re-check.

3. **Per-handshake is sufficient** (the open decision), because:
   - `canvases.owner_id` is immutable in practice. It is set at creation and
     never reassigned — `CanvasRepo.save_nodes_and_edges` (the only update
     path) mutates node/edge fields only, and there is no owner-transfer
     endpoint. Ownership cannot change mid-handshake.
   - A single WS connection performs a single run action: it receives one
     prompt, then streams until the run reaches a terminal status. It never
     loops back to receive a second prompt, so "per-handshake" == "per-run"
     for this route.

4. **The resume (`run_id` replay) path does not widen the window.** The path
   `conversation_id`'s ownership is verified first; only then is the run
   fetched and required to belong to that same conversation
   (`existing_run.conversation_id != conversation_id` → 400). A foreign run_id
   cannot escape the owned-conversation boundary, so replay is gated
   transitively by the per-handshake ownership check.

## Consequences

- A logged-out client cannot open the run WS; the upgrade is denied before
  `accept()`.
- A user cannot start or replay a run against a conversation in another user's
  canvas: rejected with `{"type":"error","message":"Conversation not found"}`
  (same message for foreign and missing, so existence is not leaked) and no
  run is created.
- A user replaying a foreign run_id against their own conversation is rejected
  with `400: Run does not belong to conversation` and no run created.
- Frontend needs no change: `useChatWebSocket` opens the socket with
  `new WebSocket(url)` and no options, and browsers attach the session cookie
  automatically on same-origin upgrades (the dev/compose proxy is same-origin;
  #36's `credentials: 'include'` wrapper covers the REST path).

## Verification

`backend/tests/test_routes_execute_ws_auth.py` — real-DB, real-cookie tests:
unauthenticated upgrade rejected; cross-user run rejected with no run created;
own-user run proceeds; cross-user replay via own conversation rejected.