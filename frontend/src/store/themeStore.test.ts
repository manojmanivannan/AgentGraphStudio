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

describe("themeStore", () => {
  beforeEach(() => {
    vi.resetModules();
    document.documentElement.className = "";
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.style.colorScheme = "";
    mockLocalStorage.clear();
    vi.restoreAllMocks();
  });

  it("should initialize with default 'dark' when no settings are present", async () => {
    const { useThemeStore } = await import("./themeStore");
    const store = useThemeStore.getState();
    expect(store.theme).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("should initialize with theme from localStorage if present", async () => {
    mockLocalStorage.setItem("agent-builder-theme", "light");
    const { useThemeStore } = await import("./themeStore");
    const store = useThemeStore.getState();
    expect(store.theme).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("should initialize with theme from prefers-color-scheme if localStorage is missing", async () => {
    const originalMatchMedia = window.matchMedia;
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

    const { useThemeStore } = await import("./themeStore");
    const store = useThemeStore.getState();
    expect(store.theme).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");

    window.matchMedia = originalMatchMedia;
  });

  it("should toggle theme correctly", async () => {
    vi.useFakeTimers();
    const { useThemeStore } = await import("./themeStore");
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

  it("should set specific theme correctly", async () => {
    vi.useFakeTimers();
    const { useThemeStore } = await import("./themeStore");
    
    useThemeStore.getState().setTheme("light");
    expect(useThemeStore.getState().theme).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(mockStore["agent-builder-theme"]).toBe("light");

    useThemeStore.getState().setTheme("dark");
    expect(useThemeStore.getState().theme).toBe("dark");

    vi.useRealTimers();
  });

  it("should handle localStorage throwing error on getItem/setItem", async () => {
    mockLocalStorage.getItem.mockImplementationOnce(() => {
      throw new Error("SecurityError");
    });
    mockLocalStorage.setItem.mockImplementationOnce(() => {
      throw new Error("SecurityError");
    });

    const { useThemeStore } = await import("./themeStore");
    const store = useThemeStore.getState();
    expect(store.theme).toBe("dark");

    // Toggle should still work without crashing even if localStorage throws
    useThemeStore.getState().toggleTheme();
    expect(useThemeStore.getState().theme).toBe("light");
  });
});
