## Parent PRD

`issues/prd.md`

## What to build

Full vertical test coverage for the `CanvasToolbar` component — from isolated component tests through to browser-level E2E.

**Component tests** (`CanvasToolbar.test.tsx`, Vitest + RTL):
- Add agent button appends an agent node to the store with a sequential default name
- Add tool button appends a tool node to the store with a sequential default name
- Clear button sets nodes and edges to empty arrays
- Renaming the canvas name input calls `setName` and updates the store
- Export button serialises the canvas and triggers a file download (`URL.createObjectURL`)
- Import: file change handler parses JSON, calls `importCanvas` API (MSW mock), and updates the store
- Import failure (bad JSON or API error) logs an error without crashing

**E2E spec** (`e2e/canvas-toolbar.spec.ts`, Playwright):
- Uses `canvasWithWorkflow` fixture to open a seeded canvas
- Clicking "+ Agent" causes a new node with "Agent" in its name to appear in the ReactFlow canvas
- Clicking "+ Tool" causes a new node with "Tool" in its name to appear
- Renaming the canvas via the toolbar name input updates the visible title
- Clicking "Clear" removes all nodes from the canvas view
- Export downloads a `.json` file (verify via download event)

## Acceptance criteria

- [ ] `CanvasToolbar.test.tsx` exists with ≥7 passing component tests covering all toolbar actions
- [ ] `e2e/canvas-toolbar.spec.ts` exists with ≥5 passing E2E tests
- [ ] All new component tests pass in `npm run test`
- [ ] All new E2E tests pass in `npm run test:e2e`
- [ ] Coverage for `CanvasToolbar.tsx` reaches ≥80% lines

## Blocked by

- Blocked by `issues/002-playwright-shared-fixtures.md`

## User stories addressed

- User story 8 — add agent node via toolbar
- User story 9 — agent node appears on canvas immediately
- User story 10 — add tool node via toolbar
- User story 11 — tool node appears on canvas
- User story 12 — sequential default naming
- User story 13 — rename canvas
- User story 14 — clear canvas
- User story 15 — export as JSON
- User story 16 — import from JSON file
- User story 17 — imported canvas replaces current state
- User story 18 — import failure handled gracefully
