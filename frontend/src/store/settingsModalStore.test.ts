import { describe, it, expect, beforeEach } from "vitest";
import { useSettingsModalStore } from "@/store/settingsModalStore";

describe("settingsModalStore", () => {
  beforeEach(() => {
    useSettingsModalStore.getState().reset();
  });

  it("starts closed on the default section", () => {
    const state = useSettingsModalStore.getState();
    expect(state.open).toBe(false);
    expect(state.section).toBe("account");
    expect(state.isOpen()).toBe(false);
  });

  it("openSettings() opens on the default section", () => {
    useSettingsModalStore.getState().openSettings();
    const state = useSettingsModalStore.getState();
    expect(state.open).toBe(true);
    expect(state.section).toBe("account");
    expect(state.isOpen()).toBe(true);
  });

  it("openSettings(section) opens on the requested section", () => {
    useSettingsModalStore.getState().openSettings("providers");
    const state = useSettingsModalStore.getState();
    expect(state.open).toBe(true);
    expect(state.section).toBe("providers");
  });

  it("openSettings does not reset the section when called with none mid-session", () => {
    // Close preserves the last section, so reopening without an explicit
    // section returns the user where they left off.
    useSettingsModalStore.getState().openSettings("appearance");
    useSettingsModalStore.getState().closeSettings();
    useSettingsModalStore.getState().openSettings();
    expect(useSettingsModalStore.getState().section).toBe("appearance");
  });

  it("openSettings(section) forces the section even after a prior session", () => {
    useSettingsModalStore.getState().openSettings("appearance");
    useSettingsModalStore.getState().closeSettings();
    useSettingsModalStore.getState().openSettings("providers");
    expect(useSettingsModalStore.getState().section).toBe("providers");
  });

  it("setSection changes the section while keeping the dialog open", () => {
    useSettingsModalStore.getState().openSettings("account");
    useSettingsModalStore.getState().setSection("appearance");
    const state = useSettingsModalStore.getState();
    expect(state.open).toBe(true);
    expect(state.section).toBe("appearance");
  });

  it("closeSettings closes but preserves the last section", () => {
    useSettingsModalStore.getState().openSettings("providers");
    useSettingsModalStore.getState().closeSettings();
    const state = useSettingsModalStore.getState();
    expect(state.open).toBe(false);
    expect(state.section).toBe("providers");
    expect(state.isOpen()).toBe(false);
  });

  it("closeSettings when already closed is a no-op", () => {
    useSettingsModalStore.getState().closeSettings();
    expect(useSettingsModalStore.getState().open).toBe(false);
  });

  it("reset returns to the initial closed state", () => {
    useSettingsModalStore.getState().openSettings("providers");
    useSettingsModalStore.getState().reset();
    const state = useSettingsModalStore.getState();
    expect(state.open).toBe(false);
    expect(state.section).toBe("account");
  });
});