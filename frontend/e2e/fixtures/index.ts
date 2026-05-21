/**
 * Shared Playwright fixtures for E2E specs.
 *
 * Usage:
 *   import { test, expect } from '@/e2e/fixtures';
 *
 * Available fixtures:
 *   - canvasWithWorkflow: WorkflowNodeIds — seeds a full workflow canvas and opens it
 *   - wsFixture: WsHelper — intercepts the execution WebSocket and provides triggerRun()
 */
export { test, expect, type WorkflowNodeIds } from "./websocket";
export type { WsHelper, WsFixture } from "./websocket";
export type { CanvasFixture } from "./canvas";
