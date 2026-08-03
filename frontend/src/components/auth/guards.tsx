import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";

/**
 * Route guard for protected app routes (canvas editor, chat, observability,
 * landing). Unauthenticated users are redirected to /login, preserving the
 * path they tried to reach so we can send them back after login.
 *
 * The boot hydration in {@link App} resolves the auth status to either
 * "authenticated" or "unauthenticated" before these routes render, so this guard
 * only ever sees those two states — "unknown" is handled by the boot splash.
 */
export function RequireAuth() {
  const status = useAuthStore((s) => s.status);
  const location = useLocation();
  if (status === "unauthenticated") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

/**
 * Guard for the auth routes (/login, /register). Authenticated users are
 * bounced to the app so they can't re-login through the URL.
 */
export function RedirectIfAuthed() {
  const status = useAuthStore((s) => s.status);
  if (status === "authenticated") {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}