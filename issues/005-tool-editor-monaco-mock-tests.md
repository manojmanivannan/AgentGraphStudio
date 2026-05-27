## Parent PRD

`issues/prd.md`

## What to build

Full vertical test coverage for `ToolEditor` — including a shared Monaco Editor mock for Vitest, component tests, and E2E.

**Monaco Editor mock** (global Vitest mock):
- Add a file at `src/test/mocks/monaco.ts` that exports a mock `Editor` component accepting `value`, `onChange`, `height`, `options`, and `defaultLanguage` props.
- The mock renders a `<textarea data-testid="tool-code-editor" />` that forwards `value` and calls `onChange` on change events — fully functional in jsdom without WebGL.
- Register the mock via `vi.mock('@monaco-editor/react', ...)` in the Vitest global setup or inline in each test file that needs it.

**Component tests** (`ToolEditor.test.tsx`, Vitest + RTL):
- Shows placeholder "Select a tool node to edit its code" when no tool node is selected
- Renders name input and Monaco editor (via mock) when a tool node is selected
- Typing in the name input updates the node's `name` field in the store
- Simulating a change event on the code editor (textarea mock) updates the node's `code` field in the store
- Changing the code updates the tool node's preview on the canvas (first 3 lines reflected)

**E2E spec** (`e2e/tool-editor.spec.ts`, Playwright):
- Uses `canvasWithWorkflow` fixture
- Clicking the WebSearch tool node opens `ToolEditor` in the properties panel
- The tool name input is pre-populated with "WebSearch"
- Editing the tool name in the panel immediately updates the node title on the canvas
- Typing Python code in the Monaco editor updates the code preview on the tool node (first 3 lines)

## Acceptance criteria

- [ ] Monaco mock exists at `src/test/mocks/monaco.ts` and renders a `<textarea>` in jsdom
- [ ] `ToolEditor.test.tsx` exists with ≥5 passing component tests
- [ ] `e2e/tool-editor.spec.ts` exists with ≥3 passing E2E tests
- [ ] Code edits in E2E verifiably update the code preview on the tool node
- [ ] Coverage for `ToolEditor.tsx` reaches ≥80% lines
- [ ] All tests pass in CI

## Blocked by

- Blocked by `issues/002-playwright-shared-fixtures.md`

## User stories addressed

- User story 32 — edit tool name
- User story 33 — write Python code via Monaco editor
- User story 34 — code changes reflected in tool node preview
- User story 35 — placeholder when no tool node selected
