import { create } from "zustand";

export type UnsavedChangesChoice = "save" | "discard" | "cancel";

interface PendingPrompt {
  id: number;
  resolve: (choice: UnsavedChangesChoice) => void;
}

interface UnsavedChangesPromptState {
  pending: PendingPrompt | null;
  request: () => Promise<UnsavedChangesChoice>;
  settle: (choice: UnsavedChangesChoice) => void;
}

let nextPromptId = 1;

export const useUnsavedChangesPromptStore = create<UnsavedChangesPromptState>((set, get) => ({
  pending: null,
  request: () =>
    new Promise<UnsavedChangesChoice>((resolve) => {
      set({ pending: { id: nextPromptId++, resolve } });
    }),
  settle: (choice) => {
    get().pending?.resolve(choice);
    set({ pending: null });
  },
}));

/**
 * Promise-based 3-way prompt for leaving a canvas with unsaved changes —
 * `const choice = await promptUnsavedChanges()` resolves to
 * "save" | "discard" | "cancel". Resolves "cancel" if dismissed without an
 * explicit choice (Escape, backdrop click, or the close button), so callers
 * can treat "cancel" as "stay on the current page".
 */
export function promptUnsavedChanges(): Promise<UnsavedChangesChoice> {
  return useUnsavedChangesPromptStore.getState().request();
}
