## Parent PRD

`issues/prd.md`

## What to build

Add `data-testid` attributes to key interactive and visual elements across the production frontend components. This is a non-functional change that adds stable, semantic test hooks required by every downstream E2E spec. Without these attributes, Playwright selectors rely on fragile CSS classes or brittle text matching.

Elements to instrument:
- `AgentNode` root div — `data-testid="agent-node"`, with `data-node-id={id}` and `data-agent-type={agentType}`
- `ToolNode` root div — `data-testid="tool-node"`, with `data-node-id={id}`
- `CanvasToolbar` — `data-testid="add-agent-button"`, `data-testid="add-tool-button"`, `data-testid="clear-canvas-button"`, `data-testid="export-button"`, `data-testid="import-button"`, `data-testid="canvas-name-input"`
- `PropertiesSidebar` — `data-testid="properties-sidebar"`, `data-testid="properties-toggle"`, `data-testid="properties-close"`
- `AgentEditor` — `data-testid="agent-type-select"`, `data-testid="agent-name-input"`, `data-testid="agent-role-input"`, `data-testid="agent-instructions-input"`, `data-testid="agent-model-input"`
- `ToolEditor` — `data-testid="tool-name-input"`, `data-testid="tool-code-editor"`
- `ChatPanel` — `data-testid="chat-input"`, `data-testid="send-button"`, `data-testid="stop-button"`, `data-testid="new-conversation-button"`, `data-testid="conversation-selector"`

## Acceptance criteria

- [ ] All listed `data-testid` attributes are present in the rendered DOM for their respective elements
- [ ] `AgentNode` exposes `data-node-id` and `data-agent-type` attributes so specs can assert on specific nodes
- [ ] `ToolNode` exposes `data-node-id` so specs can assert on specific nodes
- [ ] No visual or behavioural changes — this is instrumentation only
- [ ] Existing 38 unit/component tests still pass after the changes

## Blocked by

None — can start immediately.

## User stories addressed

Foundation for all user stories in the PRD. Directly enables stable selectors for:
- User stories 8–18 (toolbar)
- User stories 19–35 (properties + editors)
- User stories 36–53 (chat panel)
- User stories 54–59 (canvas nodes)
