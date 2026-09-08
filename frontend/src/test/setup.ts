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

// Node 22+ ships an experimental webstorage global whose `localStorage` getter
// returns undefined unless `--localstorage-file` is passed. Vitest copies that
// broken getter onto the jsdom window, shadowing jsdom's working Storage
// implementation, so tests that touch localStorage (e.g. AppearanceSection)
// crash with "Cannot read properties of undefined". Detect the inert getter
// and replace it with a spec-compliant in-memory storage.
const localStorageUnavailable = (() => {
  try {
    const existing = (globalThis as any).localStorage;
    return existing == null || typeof existing.getItem !== "function";
  } catch {
    return true;
  }
})();

if (localStorageUnavailable) {
  const createInMemoryStorage = () => {
    const backing = new Map<string, string>();
    return {
      getItem: (key: string) => (backing.has(key) ? backing.get(key)! : null),
      setItem: (key: string, value: string) => {
        backing.set(String(key), String(value));
      },
      removeItem: (key: string) => {
        backing.delete(key);
      },
      clear: () => {
        backing.clear();
      },
      key: (index: number) => Array.from(backing.keys())[index] ?? null,
      get length() {
        return backing.size;
      },
    };
  };
  const storage = createInMemoryStorage();
  Object.defineProperty(globalThis, "localStorage", {
    value: storage,
    configurable: true,
    writable: true,
  });
  Object.defineProperty(globalThis, "sessionStorage", {
    value: createInMemoryStorage(),
    configurable: true,
    writable: true,
  });
  if (typeof window !== "undefined") {
    Object.defineProperty(window, "localStorage", {
      value: storage,
      configurable: true,
      writable: true,
    });
    Object.defineProperty(window, "sessionStorage", {
      value: (globalThis as any).sessionStorage,
      configurable: true,
      writable: true,
    });
  }
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

// Mock scrollIntoView which is not available in jsdom
Element.prototype.scrollIntoView = () => { };

afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
