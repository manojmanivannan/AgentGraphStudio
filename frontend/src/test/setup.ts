import "@testing-library/jest-dom";
import { afterAll, afterEach, beforeAll } from "vitest";
import { cleanup } from "@testing-library/react";
import { server } from "./mocks/server";

// Suppress Node 22+ ExperimentalWarning about localStorage in jsdom
const originalEmit = process.emit;
process.emit = function (this: any, event: any, ...args: any[]) {
  if (event === "warning" && args[0]?.name === "ExperimentalWarning" &&
    String(args[0]?.message ?? "").includes("localStorage")) {
    return false;
  }
  return originalEmit.apply(this, [event, ...args] as any);
} as typeof process.emit;

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

// Mock scrollIntoView which is not available in jsdom
Element.prototype.scrollIntoView = () => { };

afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
