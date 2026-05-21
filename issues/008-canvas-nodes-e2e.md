## Parent PRD

`issues/prd.md`

## What to build

Playwright E2E spec covering the visual states of Agent Nodes and Tool Nodes on the canvas — including worker/router badges, content rendering, and the active-node pulse during a mock workflow execution.

**E2E spec** (`e2e/canvas-nodes.spec.ts`, Playwright):

*Static rendering (seeded canvas):*
- The Orchestrator (router) agent node is visible with `data-testid="agent-node"` and `data-agent-type="router"`
- The Orchestrator node displays a "Router" badge
- Worker agent nodes display a "Worker" badge
- Agent node body shows the agent's role text
- The WebSearch tool node is visible with `data-testid="tool-node"`
- The WebSearch tool node shows the first 3 lines of its stub Python code in the preview area
- Clicking an agent node selects it (blue ring visible on the node)

*Active-node pulse during execution:*
- With `wsFixture` active, sending a message triggers the mock stream
- When `agent_start` (Orchestrator, `node_id=router_id`) is received, the Orchestrator node has the `animate-pulse` class
- When `handoff` transitions to Researcher (`node_id=researcher_id`), the Researcher node has `animate-pulse` and the Orchestrator no longer does
- After `run_complete`, no node has `animate-pulse`

## Acceptance criteria

- [ ] `e2e/canvas-nodes.spec.ts` exists with ≥7 passing E2E tests
- [ ] Worker and Router badges verified by text content in the node
- [ ] Code preview tested against the stub code seeded by `canvasWithWorkflow`
- [ ] Active-node pulse verified using `animate-pulse` class on the correct `[data-node-id]` element
- [ ] After run completion, `animate-pulse` is absent from all nodes
- [ ] All tests pass in `npm run test:e2e`

## Blocked by

- Blocked by `issues/002-playwright-shared-fixtures.md`

## User stories addressed

- User story 54 — Worker/Router badges on agent nodes
- User story 55 — purple vs indigo header styling (Router vs Worker)
- User story 56 — agent role and instructions in node body
- User story 57 — tool code preview (first 3 lines)
- User story 58 — active node pulses during execution
- User story 59 — selected node shows blue ring
