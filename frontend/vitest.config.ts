import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    exclude: ["e2e/**", "node_modules/**"],
    // Speed: use worker_threads (lighter than child_process forks)
    pool: "threads",
    // Speed: skip CSS processing — not needed for unit tests
    css: false,
    reporters: [
      "default",
      ["junit", { outputFile: "junit/vitest-results.xml" }],
    ],
    coverage: {
      provider: "v8",
      exclude: [
        "e2e/**",
        "src/test/**",
        "src/main.tsx",
        "src/vite-env.d.ts",
        "*.config.*",
      ],
      thresholds: {
        lines: 70,
      },
    },
  },
});
