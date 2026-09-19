import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

// vitest is configured with `css: false` (see vitest.config.ts) — jsdom never
// loads/evaluates globals.css. Instead we extract the hex values straight from
// the source and compute WCAG 1.4.3 contrast ratios ourselves, asserting the
// token/theme pairings ticket #100 identified as failing now clear 4.5:1
// (regular-weight text threshold), without regressing the pairings that
// already passed.
const cssPath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "globals.css",
);
const css = readFileSync(cssPath, "utf-8");

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ];
}

function srgbToLinear(c: number): number {
  const v = c / 255;
  return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}

function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex);
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b);
}

function contrast(hexA: string, hexB: string): number {
  const l1 = relativeLuminance(hexA);
  const l2 = relativeLuminance(hexB);
  const [lighter, darker] = l1 > l2 ? [l1, l2] : [l2, l1];
  return (lighter + 0.05) / (darker + 0.05);
}

// Extracts `--token: #hex;` from a specific block of CSS (the `@theme { ... }`
// default/dark block, or a `html[data-theme="light"] { ... }` block).
function extractToken(block: string, token: string): string {
  const re = new RegExp(`--${token}:\\s*(#[0-9a-fA-F]{6})\\s*;`);
  const match = block.match(re);
  expect(match, `expected --${token} to be defined as a hex value in the given block`).not.toBeNull();
  return match![1];
}

function extractBlock(source: string, startMarker: string): string {
  const start = source.indexOf(startMarker);
  expect(start, `expected to find block starting with "${startMarker}"`).toBeGreaterThan(-1);
  const openBrace = source.indexOf("{", start);
  let depth = 0;
  for (let i = openBrace; i < source.length; i++) {
    if (source[i] === "{") depth++;
    if (source[i] === "}") {
      depth--;
      if (depth === 0) return source.slice(openBrace, i + 1);
    }
  }
  throw new Error(`Unterminated block starting with "${startMarker}"`);
}

const darkTheme = extractBlock(css, "@theme {");
const lightTheme = extractBlock(css, 'html[data-theme="light"] {');

const WCAG_AA_TEXT = 4.5;

describe("globals.css contrast (ticket #100)", () => {
  it("dark-mode --color-text-tertiary clears 4.5:1 against --color-base and --color-surface", () => {
    const tertiary = extractToken(darkTheme, "color-text-tertiary");
    const base = extractToken(darkTheme, "color-base");
    const surface = extractToken(darkTheme, "color-surface");
    expect(contrast(tertiary, base)).toBeGreaterThanOrEqual(WCAG_AA_TEXT);
    expect(contrast(tertiary, surface)).toBeGreaterThanOrEqual(WCAG_AA_TEXT);
  });

  it("light-mode --color-text-tertiary clears 4.5:1 against --color-base and --color-surface", () => {
    const tertiary = extractToken(lightTheme, "color-text-tertiary");
    const base = extractToken(lightTheme, "color-base");
    const surface = extractToken(lightTheme, "color-surface");
    expect(contrast(tertiary, base)).toBeGreaterThanOrEqual(WCAG_AA_TEXT);
    expect(contrast(tertiary, surface)).toBeGreaterThanOrEqual(WCAG_AA_TEXT);
  });

  it("light-mode --color-accent-dim clears 4.5:1 for white text (the .btn-primary / .chat-bubble-user fix)", () => {
    const accentDim = extractToken(lightTheme, "color-accent-dim");
    expect(contrast("#ffffff", accentDim)).toBeGreaterThanOrEqual(WCAG_AA_TEXT);
  });

  it("does not regress: light-mode --color-accent still clears 4.5:1 for black text (theme-toggle usage in App.tsx)", () => {
    const accent = extractToken(lightTheme, "color-accent");
    expect(contrast("#000000", accent)).toBeGreaterThanOrEqual(WCAG_AA_TEXT);
  });

  it(".btn-primary uses --color-accent-dim (not the shared --color-accent) for its light-mode background", () => {
    const lightBtnPrimary = extractBlock(css, 'html[data-theme="light"] .btn-primary {');
    expect(lightBtnPrimary).toMatch(/background-color:\s*var\(--color-accent-dim\)/);
  });

  it(".btn-primary:hover keeps white-text contrast \u2265 4.5:1 in light mode (darkens accent-dim, not accent-bright)", () => {
    const lightBtnPrimaryHover = extractBlock(css, 'html[data-theme="light"] .btn-primary:hover {');
    expect(lightBtnPrimaryHover).toMatch(/color-mix\(in srgb, var\(--color-accent-dim\)/);
    // accent-bright fails white-text contrast (2.49:1) — guard against regressing to it.
    expect(lightBtnPrimaryHover).not.toMatch(/var\(--color-accent-bright\)/);
  });

  it(".chat-bubble-user overrides to --color-accent-dim in light mode only, leaving dark mode's passing pairing untouched", () => {
    const base = extractBlock(css, ".chat-bubble-user {");
    expect(base).toMatch(/background-color:\s*var\(--color-accent\)\s*;/);
    const lightOverride = extractBlock(css, 'html[data-theme="light"] .chat-bubble-user {');
    expect(lightOverride).toMatch(/background-color:\s*var\(--color-accent-dim\)/);
  });
});
