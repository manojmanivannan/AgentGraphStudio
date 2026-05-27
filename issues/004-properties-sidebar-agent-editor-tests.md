## Parent PRD

`issues/prd.md`

## What to build

Full vertical test coverage for `PropertiesSidebar` and `AgentEditor` — from isolated component tests through to browser-level E2E.

**Component tests** (Vitest + RTL):

`PropertiesSidebar.test.tsx`:
- Collapsed by default; shows only the settings toggle icon
- Clicking the toggle expands the panel
- When an agent node is selected in the store, `AgentEditor` is rendered (mock the child)
- When a tool node is selected in the store, `ToolEditor` is rendered (mock the child)
- When no node is selected and panel is open, shows "Select a node to edit its properties" placeholder
- Clicking X closes the panel and deselects the node
- When collapsed with a selected node, a blue indicator dot is visible

`AgentEditor.test.tsx`:
- Shows placeholder "Select an agent node to edit its properties" when no agent is selected
- Renders name, role, instructions, model inputs and type dropdown for a selected agent node
- Typing in the name input updates the node's `name` field in the store
- Changing the type select to "Router" updates `agentType` in the store
- Editing role, instructions, and model inputs each update the corresponding store field
- Model input has a datalist with predefined suggestions

**E2E spec** (`e2e/properties-sidebar.spec.ts`, Playwright):
- Uses `canvasWithWorkflow` fixture
- Clicking the settings icon opens the properties panel
- Clicking the Orchestrator (router) agent node opens `AgentEditor` with its current values pre-populated
- Changing the agent type to "Worker" in the dropdown immediately updates the node's badge on the canvas
- Editing the agent name updates the node title visible on the canvas
- Clicking X closes the panel
- Clicking a worker agent node then a tool node switches the editor from AgentEditor to ToolEditor

## Acceptance criteria

- [ ] `PropertiesSidebar.test.tsx` exists with ≥7 passing component tests
- [ ] `AgentEditor.test.tsx` exists with ≥7 passing component tests
- [ ] `e2e/properties-sidebar.spec.ts` exists with ≥5 passing E2E tests
- [ ] Editing an agent name in E2E verifiably updates the node title on the canvas
- [ ] Coverage for `PropertiesSidebar.tsx` and `AgentEditor.tsx` reaches ≥80% lines
- [ ] All tests pass in CI

## Blocked by

- Blocked by `issues/002-playwright-shared-fixtures.md`

## User stories addressed

- User story 19 — sidebar collapsed by default, expandable
- User story 20 — AgentEditor shown when agent selected
- User story 21 — ToolEditor shown when tool selected
- User story 22 — placeholder when no node selected
- User story 23 — X button closes panel
- User story 24 — selection indicator dot when collapsed
- User story 25 — change agent type Worker/Router
- User story 26 — edit agent name
- User story 27 — edit agent role
- User story 28 — edit agent instructions
- User story 29 — select/type LLM model
- User story 30 — edits reflected on canvas node live
- User story 31 — placeholder when no agent selected
