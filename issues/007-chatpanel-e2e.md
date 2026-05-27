## Parent PRD

`issues/prd.md`

## What to build

Playwright E2E spec covering the full ChatPanel interaction flow in a real browser, with WebSocket execution mocked via `wsFixture`.

**E2E spec** (`e2e/chat-panel.spec.ts`, Playwright):

*Conversation management:*
- Opening a seeded canvas shows "Select or create a conversation" placeholder in the chat
- Clicking the conversation selector opens the dropdown
- Clicking "New Conversation" creates a conversation and shows it as selected
- An existing conversation can be selected from the list and its name appears in the selector
- Deleting a conversation from the list removes it from the dropdown

*Sending a message and execution stream:*
- With `wsFixture` active, typing a message and pressing Enter sends it, and the user message appears in the chat
- The loading indicator (three bouncing dots) appears while `running` is true
- `agent_start` event causes a system message "Orchestrator is working..." to appear
- `handoff` event causes "Delegating to Researcher..." to appear
- A `thought` event appears collapsed with "Thinking..." text
- Clicking the collapsed thought expands it and shows the thought content
- `tool_result` event appears with green styling
- `final_answer` event appears as an assistant message with the expected content ("Test answer")
- After `run_complete` the loading dots disappear and the send button is re-enabled

*Stop:*
- Clicking the stop button during a run closes the WebSocket; loading indicator disappears

*Node active state cross-check:*
- During a run, the node matching `node_id` in the streaming events has `data-testid="agent-node"` and the `animate-pulse` class (cross-reference with canvas-nodes spec)

## Acceptance criteria

- [ ] `e2e/chat-panel.spec.ts` exists with ≥10 passing E2E tests
- [ ] All streaming event types render correctly in a real browser
- [ ] Thought collapse/expand works in Playwright
- [ ] Stop button test closes the WS and confirms the UI returns to idle
- [ ] All tests pass in `npm run test:e2e`

## Blocked by

- Blocked by `issues/002-playwright-shared-fixtures.md`
- Blocked by `issues/006-chatpanel-component-tests.md`

## User stories addressed

- User story 36 — create new conversation (E2E layer)
- User story 37 — list conversations (E2E layer)
- User story 38 — select conversation (E2E layer)
- User story 39 — delete conversation (E2E layer)
- User story 40 — send message (E2E layer)
- User story 41 — auto-create conversation on send
- User story 42 — user message appears immediately
- User story 43 — loading indicator
- User story 44 — agent_start system messages
- User story 45 — thought collapsed by default
- User story 46 — expand/collapse thought
- User story 47 — handoff system messages
- User story 48 — tool_result messages
- User story 49 — final_answer message
- User story 50 — active node pulse during execution
- User story 51 — stop button
- User story 52 — send button disabled while running
