# Frontend test framework: Vitest + React Testing Library + Playwright + MSW

The frontend had no test infrastructure. We chose **Vitest** over Jest because Vite is the build tool — Vitest reuses the same config, alias resolution (`@/`), and transform pipeline with zero bridging. Jest requires manual ESM shims and Vite alias duplication. We chose **Playwright** over Cypress for E2E because the canvas uses `@xyflow/react` with complex pointer events, and Playwright's pointer event synthesis is more reliable for drag-and-drop flows. **MSW** is used for API mocking across all layers (Vitest component tests and Playwright) so mock handlers are written once.

## Considered Options

- **Jest** — rejected because of ESM/Vite bridging friction and duplicate alias config
- **Cypress** — rejected because of weaker pointer event support and JS-first API
- **`vi.mock()` only** — rejected in favour of MSW so mock definitions are shared between unit, component, and E2E layers

## Consequences

- Vitest and Playwright coexist in the same repo without conflict; `vitest.config.ts` is separate from `vite.config.ts`
- E2E tests start the real FastAPI backend (uvicorn) and Vite dev server via Playwright's `webServer` config
- CI runs Vitest (with 70% line coverage gate) and Playwright on every PR
