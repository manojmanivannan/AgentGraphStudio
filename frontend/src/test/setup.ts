import "@testing-library/jest-dom";
import { afterAll, afterEach, beforeAll } from "vitest";
import { cleanup } from "@testing-library/react";
import { server } from "./mocks/server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

// Mock scrollIntoView which is not available in jsdom
Element.prototype.scrollIntoView = () => { };

afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
