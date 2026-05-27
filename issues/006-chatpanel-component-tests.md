## Parent PRD

`issues/prd.md`

## What to build

Vitest + RTL component tests for `ChatPanel` covering all execution event types and conversation management. The WebSocket is mocked in jsdom using a fake `WebSocket` class (not MSW — MSW handles HTTP; WebSocket requires a separate in-process mock).

**Component tests** (`ChatPanel.test.tsx`, Vitest + RTL):

*Conversation management:*
- On mount with a canvas ID, `listConversations` is called and conversations are displayed in the selector
- Clicking "New Conversation" calls `createConversation` and adds it to the list
- Selecting a conversation from the list calls `getConversation` and renders its message history
- Deleting a conversation calls `deleteConversation` and removes it from the list; clears messages if it was active

*Send and auto-create:*
- Typing a message and pressing Enter calls `createConversation` then opens a WebSocket connection
- The user message appears in the chat immediately upon send
- The send button is disabled while `running` is true
- The input field is disabled when `canvasId` is null
- Sending when a conversation is already active skips `createConversation` and directly opens WebSocket

*Streaming event rendering:*
- `agent_start` event renders a system message "X is working..."
- `thought` event renders collapsed by default with "Thinking..." placeholder
- Clicking a collapsed thought expands it to show the content
- Clicking an expanded thought collapses it again
- `handoff` event renders a system message "Delegating to Y..."
- `tool_result` event renders an assistant message with green styling
- `final_answer` event renders an assistant message
- `run_complete` event ends the running state (send button re-enabled, loading dots hidden)
- `error` event renders a red system message and ends running state

*Stop button:*
- Stop button is visible and enabled while `running` is true
- Clicking stop closes the WebSocket and re-enables the send button

**Fake WebSocket setup:**
- Create a `FakeWebSocket` class in `src/test/mocks/websocket.ts` that captures `send()` calls and exposes a `simulateMessage(data)` helper. Register it as `window.WebSocket` in tests that need it, and restore after each test.

## Acceptance criteria

- [ ] `ChatPanel.test.tsx` exists with ≥15 passing component tests covering all event types and conversation flows
- [ ] `src/test/mocks/websocket.ts` provides a reusable `FakeWebSocket` test helper
- [ ] All thought collapse/expand interactions are covered
- [ ] Stop button test verifies WebSocket `.close()` is called
- [ ] MSW handlers for conversation API (`POST`, `GET`, `DELETE /api/canvases/:id/conversations`) are added to `src/test/mocks/handlers.ts`
- [ ] Coverage for `ChatPanel.tsx` reaches ≥70% lines
- [ ] All tests pass in `npm run test`

## Blocked by

- Blocked by `issues/001-data-testid-instrumentation.md`

## User stories addressed

- User story 36 — create new conversation
- User story 37 — list existing conversations
- User story 38 — select conversation and see history
- User story 39 — delete conversation
- User story 40 — send message via Enter or button
- User story 41 — auto-create conversation on first send
- User story 42 — user message appears immediately
- User story 43 — loading indicator while running
- User story 44 — agent_start events as system messages
- User story 45 — thought events collapsed by default
- User story 46 — expand/collapse thought messages
- User story 47 — handoff events as system messages
- User story 48 — tool_result events as assistant messages
- User story 49 — final_answer as assistant message
- User story 51 — stop button cancels run
- User story 52 — send button disabled while running
- User story 53 — input disabled when no canvas
