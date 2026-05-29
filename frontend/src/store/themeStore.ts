import { create } from "zustand";

type Theme = "dark" | "light";

interface ThemeState {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
}

function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  try {
    const stored = localStorage.getItem("agent-builder-theme") as Theme | null;
    if (stored === "dark" || stored === "light") return stored;
  } catch {
    // localStorage unavailable (test env, SSR, privacy mode)
  }
  try {
    if (window.matchMedia?.("(prefers-color-scheme: light)").matches) return "light";
  } catch {
    // matchMedia unavailable
  }
  return "dark";
}

function applyThemeToDocument(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.style.colorScheme = theme;
}

function transitionTheme(theme: Theme) {
  const root = document.documentElement;
  root.classList.add("theme-transition");
  applyThemeToDocument(theme);
  // Remove transition class after animation completes to avoid
  // interfering with other transitions during normal interaction
  setTimeout(() => root.classList.remove("theme-transition"), 400);
}

function persistTheme(theme: Theme) {
  try {
    localStorage.setItem("agent-builder-theme", theme);
  } catch {
    // localStorage unavailable
  }
}

export const useThemeStore = create<ThemeState>((set, get) => {
  const initial = getInitialTheme();
  if (typeof window !== "undefined") {
    applyThemeToDocument(initial);
  }

  return {
    theme: initial,
    toggleTheme: () => {
      const next = get().theme === "dark" ? "light" : "dark";
      persistTheme(next);
      transitionTheme(next);
      set({ theme: next });
    },
    setTheme: (theme: Theme) => {
      persistTheme(theme);
      transitionTheme(theme);
      set({ theme });
    },
  };
});