import { beforeEach, describe, expect, it, vi } from "vitest";

// Define a robust localStorage mock to avoid Node v22+ experimental localStorage issues/warnings
const mockStore: Record<string, string> = {};
const mockLocalStorage = {
  getItem: vi.fn((key: string) => mockStore[key] || null),
  setItem: vi.fn((key: string, value: string) => {
    mockStore[key] = value.toString();
  }),
  clear: vi.fn(() => {
    for (const key in mockStore) {
      delete mockStore[key];
    }
  }),
  removeItem: vi.fn((key: string) => {
    delete mockStore[key];
  }),
  length: 0,
  key: vi.fn((index: number) => null),
};

Object.defineProperty(global, "localStorage", {
  value: mockLocalStorage,
  writable: true,
  configurable: true,
});

if (typeof window !== "undefined") {
  Object.defineProperty(window, "localStorage", {
    value: mockLocalStorage,
    writable: true,
    configurable: true,
  });
}

// Default matchMedia mock (dark preference)
const darkMatchMedia = vi.fn().mockImplementation((query) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: vi.fn(),
  removeListener: vi.fn(),
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  dispatchEvent: vi.fn(),
} as any));

window.matchMedia = darkMatchMedia;

// Import once — most tests use the default (dark) initial state
import { useThemeStore } from "./themeStore";

describe("themeStore", () => {
  beforeEach(() => {
    document.documentElement.className = "";
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.style.colorScheme = "";
    mockLocalStorage.clear();
    vi.restoreAllMocks();
    // Reset matchMedia to dark default
    window.matchMedia = darkMatchMedia;
    // Reset store to default dark theme (clears localStorage first, then sets)
    useThemeStore.getState().setTheme("dark");
    // Clear localStorage again so tests that set localStorage values aren't polluted
    mockLocalStorage.clear();
  });

  it("should initialize with default 'dark' when no settings are present", () => {
    const store = useThemeStore.getState();
    expect(store.theme).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("should initialize with theme from localStorage if present", async () => {
    mockLocalStorage.setItem("agent-builder-theme", "light");
    // Need to reset module to pick up new localStorage value
    vi.resetModules();
    const { useThemeStore: freshStore } = await import("./themeStore");
    expect(freshStore.getState().theme).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("should initialize with theme from prefers-color-scheme if localStorage is missing", async () => {
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: query === "(prefers-color-scheme: light)",
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    } as any));

    vi.resetModules();
    const { useThemeStore: freshStore } = await import("./themeStore");
    expect(freshStore.getState().theme).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("should toggle theme correctly", () => {
    vi.useFakeTimers();
    const store = useThemeStore.getState();

    // default is dark, toggle should make it light
    expect(store.theme).toBe("dark");

    useThemeStore.getState().toggleTheme();

    expect(useThemeStore.getState().theme).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(mockStore["agent-builder-theme"]).toBe("light");
    expect(document.documentElement.classList.contains("theme-transition")).toBe(true);

    vi.advanceTimersByTime(400);
    expect(document.documentElement.classList.contains("theme-transition")).toBe(false);

    // Toggle back to dark
    useThemeStore.getState().toggleTheme();
    expect(useThemeStore.getState().theme).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(mockStore["agent-builder-theme"]).toBe("dark");

    vi.useRealTimers();
  });

  it("should set specific theme correctly", () => {
    vi.useFakeTimers();

    useThemeStore.getState().setTheme("light");
    expect(useThemeStore.getState().theme).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(mockStore["agent-builder-theme"]).toBe("light");

    useThemeStore.getState().setTheme("dark");
    expect(useThemeStore.getState().theme).toBe("dark");

    vi.useRealTimers();
  });

  it("should handle localStorage throwing error on getItem/setItem", () => {
    mockLocalStorage.getItem.mockImplementationOnce(() => {
      throw new Error("SecurityError");
    });
    mockLocalStorage.setItem.mockImplementationOnce(() => {
      throw new Error("SecurityError");
    });

    // Store already imported with default dark — toggle should still work
    useThemeStore.getState().toggleTheme();
    expect(useThemeStore.getState().theme).toBe("light");
  });
});
