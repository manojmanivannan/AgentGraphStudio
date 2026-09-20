import { create } from "zustand";

export interface ConfirmOptions {
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Renders the confirm action in the danger color for destructive operations. */
  danger?: boolean;
}

interface PendingConfirm extends ConfirmOptions {
  id: number;
  resolve: (value: boolean) => void;
}

interface ConfirmState {
  pending: PendingConfirm | null;
  request: (options: ConfirmOptions) => Promise<boolean>;
  settle: (value: boolean) => void;
}

let nextConfirmId = 1;

export const useConfirmStore = create<ConfirmState>((set, get) => ({
  pending: null,
  request: (options) =>
    new Promise<boolean>((resolve) => {
      set({ pending: { ...options, id: nextConfirmId++, resolve } });
    }),
  settle: (value) => {
    get().pending?.resolve(value);
    set({ pending: null });
  },
}));

/**
 * Promise-based confirmation — `if (await confirm({ title })) { ... }`.
 * Replaces native `confirm()`; resolves `false` if dismissed without a choice
 * (Escape, backdrop click, or Cancel).
 */
export function confirm(options: ConfirmOptions): Promise<boolean> {
  return useConfirmStore.getState().request(options);
}
