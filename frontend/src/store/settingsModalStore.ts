import { create } from "zustand";
import type { SettingsSectionId } from "@/components/settings/registry";
import { DEFAULT_SECTION } from "@/components/settings/registry";

interface SettingsModalState {
  open: boolean;
  section: SettingsSectionId;
  isOpen: () => boolean;
  /** Open the dialog, optionally forcing a section. No argument keeps the
   *  last-viewed section (closing doesn't reset it). */
  openSettings: (section?: SettingsSectionId) => void;
  /** Close the dialog. The last-viewed section is preserved so reopening
   *  lands where the user left off. */
  closeSettings: () => void;
  setSection: (section: SettingsSectionId) => void;
  reset: () => void;
}

export const useSettingsModalStore = create<SettingsModalState>((set, get) => ({
  open: false,
  section: DEFAULT_SECTION,

  isOpen: () => get().open,

  openSettings: (section) =>
    set((s) => ({ open: true, section: section ?? s.section })),

  closeSettings: () => set({ open: false }),

  setSection: (section) => set({ section }),

  reset: () => set({ open: false, section: DEFAULT_SECTION }),
}));