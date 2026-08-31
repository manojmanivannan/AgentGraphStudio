import { Palette } from "lucide-react";
import { useThemeStore } from "@/store/themeStore";

const THEME_OPTIONS = [
  {
    id: "dark" as const,
    label: "Dark",
    description: "The default low-glare look for long sessions.",
  },
  {
    id: "light" as const,
    label: "Light",
    description: "Bright surfaces for well-lit environments.",
  },
];

/**
 * Settings dialog "Appearance" tab. Reads and writes themeStore, the same
 * store as the ThemeToggle chrome, so the two stay in sync automatically.
 */
export function AppearanceSection() {
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);

  return (
    <div className="flex flex-col gap-3">
      <section className="flex flex-col gap-3" aria-label="Appearance">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-[var(--color-text-primary)]">
          <Palette className="w-4 h-4 text-[var(--color-secondary)]" />
          Theme
        </h2>
        <div
          role="radiogroup"
          aria-label="Theme"
          className="grid grid-cols-1 sm:grid-cols-2 gap-2"
        >
          {THEME_OPTIONS.map((option) => (
            <button
              key={option.id}
              type="button"
              role="radio"
              aria-label={option.label}
              aria-checked={theme === option.id}
              onClick={() => setTheme(option.id)}
              className={`text-left p-3 rounded-xl border transition-colors ${
                theme === option.id
                  ? "border-[var(--color-accent)] bg-[var(--color-elevated)]"
                  : "border-[var(--color-border-default)] hover:bg-[var(--color-elevated)]"
              }`}
            >
              <span className="block text-sm font-medium text-[var(--color-text-primary)]">
                {option.label}
              </span>
              <span className="block text-[11px] text-[var(--color-text-tertiary)] mt-0.5">
                {option.description}
              </span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}