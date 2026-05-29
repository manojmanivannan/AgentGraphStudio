import { useThemeStore } from "@/store/themeStore";

export function ThemeToggle({ className = "" }: { className?: string }) {
  const theme = useThemeStore((s) => s.theme);
  const toggleTheme = useThemeStore((s) => s.toggleTheme);
  const isDark = theme === "dark";

  return (
    <button
      onClick={toggleTheme}
      data-testid="theme-toggle"
      aria-label={`Switch to ${isDark ? "light" : "dark"} mode`}
      className={`
        relative flex items-center w-[52px] h-[28px] rounded-full
        transition-all duration-300 ease-out cursor-pointer
        border-none outline-none
        focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-base)]
        ${isDark
          ? "bg-[#1e1e2e]"
          : "bg-[#e8e8f0]"
        }
        ${className}
      `}
    >
      {/* Star particles (dark mode) */}
      <span
        className={`
          absolute top-[5px] left-[8px] w-[2px] h-[2px] rounded-full bg-white
          transition-opacity duration-300
          ${isDark ? "opacity-60" : "opacity-0"}
        `}
      />
      <span
        className={`
          absolute top-[10px] left-[6px] w-[1.5px] h-[1.5px] rounded-full bg-white
          transition-opacity duration-500
          ${isDark ? "opacity-40" : "opacity-0"}
        `}
      />
      <span
        className={`
          absolute bottom-[7px] left-[10px] w-[1px] h-[1px] rounded-full bg-white
          transition-opacity duration-700
          ${isDark ? "opacity-50" : "opacity-0"}
        `}
      />
      <span
        className={`
          absolute top-[4px] left-[14px] w-[1.5px] h-[1.5px] rounded-full bg-white
          transition-opacity duration-400
          ${isDark ? "opacity-30" : "opacity-0"}
        `}
      />

      {/* Track glow (dark mode) */}
      <span
        className={`
          absolute inset-0 rounded-full
          transition-opacity duration-300
          ${isDark
            ? "opacity-100"
            : "opacity-0"
          }
        `}
        style={{
          background: "radial-gradient(circle at 30% 50%, rgba(139, 92, 246, 0.15) 0%, transparent 70%)",
        }}
      />

      {/* Thumb */}
      <span
        className={`
          relative z-10 flex items-center justify-center
          w-[22px] h-[22px] rounded-full
          transition-all duration-300 ease-[cubic-bezier(0.4,0,0.2,1)]
          ${isDark
            ? "translate-x-[27px] bg-[#c4b5fd] shadow-[0_0_8px_rgba(139,92,246,0.3)]"
            : "translate-x-[3px] bg-[#fbbf24] shadow-[0_0_8px_rgba(251,191,36,0.35)]"
          }
        `}
      >
        {/* Sun icon (light mode) */}
        <svg
          className={`
            absolute w-[14px] h-[14px] transition-all duration-300
            ${isDark ? "opacity-0 rotate-90 scale-50" : "opacity-100 rotate-0 scale-100"}
          `}
          viewBox="0 0 24 24"
          fill="none"
          stroke="#92400e"
          strokeWidth="2.5"
          strokeLinecap="round"
        >
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
        </svg>

        {/* Moon icon (dark mode) */}
        <svg
          className={`
            absolute w-[14px] h-[14px] transition-all duration-300
            ${isDark ? "opacity-100 rotate-0 scale-100" : "opacity-0 -rotate-90 scale-50"}
          `}
          viewBox="0 0 24 24"
          fill="#7c3aed"
          stroke="none"
        >
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      </span>
    </button>
  );
}