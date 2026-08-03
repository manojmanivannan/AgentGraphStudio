import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/test/mocks/server";
import { useAuthStore } from "./authStore";

const API = "http://localhost:8000/api";

const mockUser = {
  id: "user-1",
  email: "tester@example.com",
  created_at: "2024-01-01T00:00:00Z",
};

beforeEach(() => {
  useAuthStore.getState().reset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("authStore", () => {
  it("starts in the unknown status with no user", () => {
    const state = useAuthStore.getState();
    expect(state.status).toBe("unknown");
    expect(state.user).toBeNull();
  });

  it("setUser marks the session authenticated and stores the user", () => {
    useAuthStore.getState().setUser(mockUser);
    const state = useAuthStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.user).toEqual(mockUser);
  });

  it("clear marks the session unauthenticated and drops the user", () => {
    useAuthStore.getState().setUser(mockUser);
    useAuthStore.getState().clear();
    const state = useAuthStore.getState();
    expect(state.status).toBe("unauthenticated");
    expect(state.user).toBeNull();
  });

  it("reset returns the store to the initial unknown state", () => {
    useAuthStore.getState().setUser(mockUser);
    useAuthStore.getState().reset();
    const state = useAuthStore.getState();
    expect(state.status).toBe("unknown");
    expect(state.user).toBeNull();
  });

  describe("hydrate", () => {
    it("resolves to authenticated when /auth/me returns a user", async () => {
      server.use(
        http.get(`${API}/auth/me`, () => HttpResponse.json(mockUser))
      );
      await useAuthStore.getState().hydrate();
      const state = useAuthStore.getState();
      expect(state.status).toBe("authenticated");
      expect(state.user).toEqual(mockUser);
    });

    it("resolves to unauthenticated when /auth/me returns 401", async () => {
      server.use(
        http.get(`${API}/auth/me`, () => new HttpResponse(null, { status: 401 }))
      );
      await useAuthStore.getState().hydrate();
      const state = useAuthStore.getState();
      expect(state.status).toBe("unauthenticated");
      expect(state.user).toBeNull();
    });

    it("resolves to unauthenticated when /auth/me errors (network/server)", async () => {
      server.use(
        http.get(`${API}/auth/me`, () => new HttpResponse(null, { status: 500 }))
      );
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      await useAuthStore.getState().hydrate();
      expect(useAuthStore.getState().status).toBe("unauthenticated");
      expect(useAuthStore.getState().user).toBeNull();
      consoleSpy.mockRestore();
    });
  });
});