import { create } from "zustand";
import type { User } from "@/types";
import { getMe } from "@/lib/api";

export type AuthStatus = "unknown" | "authenticated" | "unauthenticated";

interface AuthState {
  /** The authenticated user, or null when not logged in / not yet hydrated. */
  user: User | null;
  /** Hydration + auth state. "unknown" until the boot /auth/me call resolves. */
  status: AuthStatus;
  /** Boot-time hydration via GET /auth/me. Resolves status to either side. */
  hydrate: () => Promise<void>;
  /** Mark the session authenticated (after login/register). */
  setUser: (user: User) => void;
  /** Mark the session unauthenticated and drop the user (after logout / 401). */
  clear: () => void;
  /** Return to the initial unknown state (used in tests). */
  reset: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  status: "unknown",
  hydrate: async () => {
    try {
      const user = await getMe();
      if (user) {
        set({ user, status: "authenticated" });
      } else {
        set({ user: null, status: "unauthenticated" });
      }
    } catch (err) {
      // Network/server error during hydration — treat as unauthenticated so
      // the route guard sends the user to /login rather than hanging on a
      // "unknown" splash forever.
      console.error("Failed to hydrate auth session:", err);
      set({ user: null, status: "unauthenticated" });
    }
  },
  setUser: (user) => set({ user, status: "authenticated" }),
  clear: () => set({ user: null, status: "unauthenticated" }),
  reset: () => set({ user: null, status: "unknown" }),
}));