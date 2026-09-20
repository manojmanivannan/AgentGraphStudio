import { create } from "zustand";

export type ToastVariant = "success" | "error" | "info";

export interface ToastEntry {
  id: number;
  message: string;
  variant: ToastVariant;
}

interface ToastState {
  toasts: ToastEntry[];
  show: (message: string, variant?: ToastVariant) => number;
  dismiss: (id: number) => void;
}

let nextToastId = 1;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  show: (message, variant = "info") => {
    const id = nextToastId++;
    set((state) => ({ toasts: [...state.toasts, { id, message, variant }] }));
    return id;
  },
  dismiss: (id) => {
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
  },
}));

/**
 * Imperative, fire-and-forget notice API — usable from event handlers or
 * plain async functions, not just components. Replaces native `alert()`.
 */
export const toast = {
  success: (message: string) => useToastStore.getState().show(message, "success"),
  error: (message: string) => useToastStore.getState().show(message, "error"),
  info: (message: string) => useToastStore.getState().show(message, "info"),
};
