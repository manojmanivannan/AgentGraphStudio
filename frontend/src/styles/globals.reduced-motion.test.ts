import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

// vitest is configured with `css: false` (see vitest.config.ts) — jsdom never
// loads/evaluates globals.css, so `@media (prefers-reduced-motion: reduce)`
// can't be exercised via getComputedStyle in unit tests. Instead we assert
// directly against the source that the reduced-motion block exists and
// neutralizes every animation ticket #99 identified.
const cssPath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "globals.css",
);
const css = readFileSync(cssPath, "utf-8");

function extractReducedMotionBlock(source: string): string {
  const start = source.indexOf("@media (prefers-reduced-motion: reduce)");
  expect(start, "expected a prefers-reduced-motion media query in globals.css").toBeGreaterThan(-1);

  // Walk braces from the opening `{` after the media query to find its matching `}`.
  const openBrace = source.indexOf("{", start);
  let depth = 0;
  for (let i = openBrace; i < source.length; i++) {
    if (source[i] === "{") depth++;
    if (source[i] === "}") {
      depth--;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error("Unterminated @media (prefers-reduced-motion: reduce) block");
}

describe("globals.css prefers-reduced-motion fallback", () => {
  const block = extractReducedMotionBlock(css);

  it("freezes the active-node glow to a static resting-frame box-shadow", () => {
    expect(block).toMatch(/\.glow-active-pulse\s*{[^}]*animation:\s*none\s*!important/);
    expect(block).toMatch(/\.glow-active-pulse\s*{[^}]*box-shadow:[^}]*!important/);
  });

  it("reduces entrance animations (fade-in, overlay panel, popover) to opacity-only, near-instant transitions", () => {
    for (const selector of [".animate-fade-in", ".overlay-panel", ".overlay-panel-exit", ".rail-popover"]) {
      const re = new RegExp(
        `\\${selector}\\s*{[^}]*animation:\\s*fade(Only|OutOnly)[^}]*1ms[^}]*!important`,
      );
      expect(block, `${selector} should collapse to a 1ms opacity-only animation`).toMatch(re);
    }
  });

  it("freezes the infinite-loop dot-pulse and save indicator animations", () => {
    expect(block).toMatch(/\.dot-pulse\s*{[^}]*animation:\s*none\s*!important/);
    expect(block).toMatch(/\.save-indicator-saving\s*{[^}]*animation:\s*none\s*!important/);
  });

  it("freezes the node selection ring", () => {
    expect(block).toMatch(/\.node-selected-pulse\s*{[^}]*animation:\s*none\s*!important/);
  });

  it("declares fadeOnly/fadeOutOnly keyframes used by the reduced-motion overrides", () => {
    expect(css).toMatch(/@keyframes fadeOnly\s*{/);
    expect(css).toMatch(/@keyframes fadeOutOnly\s*{/);
  });

  it("leaves hover/theme transition properties untouched (scope is animation-only)", () => {
    expect(block).not.toMatch(/transition:/);
  });

  it("declares a .dot-pulse utility class driving the dotPulse keyframe outside the media query", () => {
    expect(css).toMatch(/\.dot-pulse\s*{\s*animation:\s*dotPulse/);
  });
});
