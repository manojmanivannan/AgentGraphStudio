import { describe, expect, it } from "vitest";
import {
  DEFAULT_SECTION,
  SETTINGS_SECTIONS,
  getSettingsSection,
} from "@/components/settings/registry";

describe("settings section registry", () => {
  it("defines exactly the account, providers and appearance sections", () => {
    expect(SETTINGS_SECTIONS.map((s) => s.id)).toEqual([
      "account",
      "providers",
      "appearance",
    ]);
  });

  it("gives every section a unique id, non-empty label/description and component", () => {
    const ids = new Set<string>();
    for (const section of SETTINGS_SECTIONS) {
      expect(ids.has(section.id)).toBe(false);
      ids.add(section.id);
      expect(section.label.length).toBeGreaterThan(0);
      expect(section.description.length).toBeGreaterThan(0);
      expect(typeof section.Component).toBe("function");
      expect(section.icon).toBeDefined();
    }
  });

  it("looks a section up by id", () => {
    const providers = getSettingsSection("providers");
    expect(providers?.id).toBe("providers");
    expect(providers?.label).toBe("Providers");
  });

  it("returns undefined for unknown or missing ids", () => {
    expect(getSettingsSection("nope")).toBeUndefined();
    expect(getSettingsSection(null)).toBeUndefined();
  });

  it("defaults to the account section", () => {
    expect(DEFAULT_SECTION).toBe("account");
  });
});