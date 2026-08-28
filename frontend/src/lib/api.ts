import type {
  ActiveRunResponse,
  AuthResponse,
  CanvasListItem,
  CanvasResponse,
  CanvasSavePayload,
  Conversation,
  ConversationSummary,
  ExecutionEvent,
  ToolInspectResponse,
  ToolTestResponse,
  AgentDocument,
  ProviderSettings,
  ProviderSettingsForm,
  ProviderTestResponse,
  User,
} from "@/types";

const configuredApiHost = (import.meta.env.VITE_API_HOST as string | undefined)?.trim();
const useProxyMode = ((import.meta.env.VITE_USE_PROXY as string | undefined)?.trim() || "").toLowerCase() === "true";
const defaultApiOrigin =
  typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "http://localhost:8000";
const browserOrigin =
  typeof window !== "undefined" ? window.location.origin : "http://localhost:5173";

export const apiOrigin = configuredApiHost
  ? /^https?:\/\//.test(configuredApiHost)
    ? configuredApiHost
    : `http://${configuredApiHost}`
  : useProxyMode
    ? browserOrigin
    : defaultApiOrigin;

const API_BASE = useProxyMode ? "/api" : `${apiOrigin}/api`;

/**
 * Listeners notified when a protected data endpoint returns 401 — i.e. the
 * session cookie is missing/expired. The app shell registers one to clear the
 * stale auth store and bounce to /login. Auth endpoints (login/register/me)
 * use {@link authFetch} instead so a bad-credentials 401 doesn't trip the
 * redirect. Subscribers must never throw — they're invoked from inside the
 * fetch pipeline and a throw would break the calling API function.
 */
const unauthorizedListeners = new Set<() => void>();

export function onUnauthorized(listener: () => void): () => void {
  unauthorizedListeners.add(listener);
  return () => {
    unauthorizedListeners.delete(listener);
  };
}

function notifyUnauthorized(): void {
  for (const fn of unauthorizedListeners) {
    try {
      fn();
    } catch {
      // A listener error must not break the API call that detected the 401.
    }
  }
}

/**
 * Raw fetch that sends the auth session cookie. Used by auth endpoints
 * (login/register/logout/me) which must NOT trip the stale-session redirect —
 * a 401 here means "bad credentials" or "not logged in yet", not "session
 * expired while using the app".
 */
const authFetch = (input: string, init: RequestInit = {}): Promise<Response> =>
  fetch(input, { credentials: "include", ...init });

/**
 * Shared fetch wrapper for protected data endpoints: sends the auth session
 * cookie on every request so the server-side session resolves the current
 * user. `credentials: "include"` is required both for the same-origin dev
 * proxy and for the cross-origin (host:8000) case where the cookie was set by
 * the backend. On a 401 it notifies {@link onUnauthorized} listeners so the app
 * can clear stale auth state and redirect to /login.
 */
const apiFetch = async (input: string, init: RequestInit = {}): Promise<Response> => {
  const res = await fetch(input, { credentials: "include", ...init });
  if (res.status === 401) {
    notifyUnauthorized();
  }
  return res;
};

function isNetworkFetchError(error: unknown): error is Error {
  return error instanceof Error && /fetch|network|load failed|failed to fetch/i.test(error.message);
}

async function readErrorDetail(
  res: Response,
  fallbackMessage: string
): Promise<string> {
  const error = await res.json().catch(() => null) as { detail?: string } | null;
  return error?.detail || fallbackMessage;
}

// --- Auth ---

export async function register(email: string, password: string): Promise<User> {
  const res = await authFetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, "Failed to register"));
  }
  return ((await res.json()) as AuthResponse).user;
}

export async function login(email: string, password: string): Promise<User> {
  const res = await authFetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, "Failed to log in"));
  }
  return ((await res.json()) as AuthResponse).user;
}

export async function logout(): Promise<void> {
  const res = await authFetch(`${API_BASE}/auth/logout`, { method: "POST" });
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, "Failed to log out"));
  }
}

/**
 * Resolve the current user from the session cookie. Returns the user on 200,
 * `null` on 401 (not authenticated — the normal "no session yet" case during
 * boot hydration), and throws on any other error status.
 */
export async function getMe(): Promise<User | null> {
  const res = await authFetch(`${API_BASE}/auth/me`);
  if (res.status === 401) return null;
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, "Failed to get current user"));
  }
  return (await res.json()) as User;
}

/**
 * Change the current user's password. The backend verifies the current
 * password (422 'Current password is incorrect.' on a mismatch — deliberately
 * NOT 401, so a typo doesn't trip the global stale-session redirect) and, on
 * success, revokes every other session for the user while keeping this one.
 *
 * Uses {@link authFetch} (like login/logout/me) so a genuinely-expired session
 * 401 doesn't bounce the user to /login from within the account page.
 */
export async function changePassword(
  currentPassword: string,
  newPassword: string
): Promise<void> {
  const res = await authFetch(`${API_BASE}/auth/change-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, "Failed to change password"));
  }
}

/**
 * Revoke every session for the current user except the calling one. Returns
 * the number of sessions that were destroyed. Uses {@link authFetch} for the
 * same reason as {@link changePassword}.
 */
export async function logoutOtherSessions(): Promise<{ revoked: number }> {
  const res = await authFetch(`${API_BASE}/auth/logout-other-sessions`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, "Failed to log out other sessions"));
  }
  return (await res.json()) as { revoked: number };
}

// --- Provider settings ---

export async function getProviderSettings(): Promise<ProviderSettings> {
  const res = await apiFetch(`${API_BASE}/settings/provider`);
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, "Failed to load provider settings"));
  }
  return (await res.json()) as ProviderSettings;
}

/**
 * Persist provider settings. `apiKey` of `undefined` keeps the stored key,
 * `""` clears it. `confirmReindex` is required by the backend when the
 * embedding dimension changes (it purges RAG chunks and stored memories).
 */
export async function updateProviderSettings(
  form: ProviderSettingsForm,
  options: { apiKey?: string; confirmReindex?: boolean } = {}
): Promise<ProviderSettings> {
  const res = await apiFetch(`${API_BASE}/settings/provider`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...form,
      api_key: options.apiKey ?? null,
      confirm_reindex: options.confirmReindex ?? false,
    }),
  });
  if (!res.ok) {
    const error = new Error(
      await readErrorDetail(res, "Failed to save provider settings")
    ) as Error & { status?: number };
    error.status = res.status;
    throw error;
  }
  return (await res.json()) as ProviderSettings;
}

export async function testProviderSettings(
  form: ProviderSettingsForm,
  apiKey?: string
): Promise<ProviderTestResponse> {
  const res = await apiFetch(`${API_BASE}/settings/provider/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...form, api_key: apiKey ?? null }),
  });
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, "Failed to test provider settings"));
  }
  return (await res.json()) as ProviderTestResponse;
}

export async function createCanvas(
  name = "Untitled Canvas"
): Promise<CanvasResponse> {
  const res = await apiFetch(`${API_BASE}/canvases`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error("Failed to create canvas");
  return res.json();
}

export async function listCanvases(): Promise<CanvasListItem[]> {
  const res = await apiFetch(`${API_BASE}/canvases`);
  if (!res.ok) throw new Error("Failed to list canvases");
  return res.json();
}

export async function getCanvas(id: string): Promise<CanvasResponse> {
  const res = await apiFetch(`${API_BASE}/canvases/${id}`);
  if (!res.ok) throw new Error("Failed to get canvas");
  return res.json();
}

export async function saveCanvas(
  id: string,
  payload: CanvasSavePayload
): Promise<CanvasResponse> {
  const res = await apiFetch(`${API_BASE}/canvases/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Failed to save canvas");
  return res.json();
}

export async function deleteCanvas(id: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/canvases/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete canvas");
}

export async function exportCanvas(id: string): Promise<CanvasResponse> {
  const res = await apiFetch(`${API_BASE}/canvases/${id}/export`);
  if (!res.ok) throw new Error("Failed to export canvas");
  return res.json();
}

export async function exportCanvasZip(id: string): Promise<Blob> {
  const res = await apiFetch(`${API_BASE}/canvases/${id}/export-zip`);
  if (!res.ok) throw new Error("Failed to export canvas ZIP");
  return res.blob();
}

export async function importCanvas(
  payload: CanvasSavePayload
): Promise<CanvasResponse> {
  const res = await apiFetch(`${API_BASE}/canvases/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Failed to import canvas");
  return res.json();
}

export async function importCanvasZip(file: File): Promise<CanvasResponse> {
  const createRequestInit = (): RequestInit => {
    const formData = new FormData();
    formData.append("file", file);
    return {
      method: "POST",
      body: formData,
    };
  };

  let res: Response;
  try {
    res = await apiFetch(`${API_BASE}/canvases/import-zip`, createRequestInit());
  } catch {

    try {
      res = await apiFetch(`/api/canvases/import-zip`, createRequestInit());
    } catch {
      throw new Error(
        "Failed to import canvas ZIP. Could not reach the backend import endpoint."
      );
    }
  }

  if (!res.ok) {
    if (res.status >= 500) {
      try {
        const fallbackRes = await apiFetch(`/api/canvases/import-zip`, createRequestInit());
        if (!fallbackRes.ok) {
          throw new Error(await readErrorDetail(fallbackRes, "Failed to import canvas ZIP"));
        }
        return fallbackRes.json();
      } catch (error) {
        if (!isNetworkFetchError(error)) throw error;
      }
    }

    throw new Error(await readErrorDetail(res, "Failed to import canvas ZIP"));
  }
  return res.json();
}

export async function createConversation(
  canvasId: string,
  name = "New Conversation"
): Promise<Conversation> {
  const res = await apiFetch(
    `${API_BASE}/canvases/${canvasId}/conversations`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }
  );
  if (!res.ok) throw new Error("Failed to create conversation");
  return res.json();
}

export async function listConversations(
  canvasId: string
): Promise<ConversationSummary[]> {
  const url = `${API_BASE}/canvases/${canvasId}/conversations?_=${Date.now()}`;
  const res = await apiFetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to list conversations");
  return res.json();
}

export async function getConversation(
  canvasId: string,
  conversationId: string
): Promise<Conversation> {
  const url = `${API_BASE}/canvases/${canvasId}/conversations/${conversationId}?_=${Date.now()}`;
  const res = await apiFetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to get conversation");
  return res.json();
}

export async function getConversationById(
  conversationId: string
): Promise<Conversation> {
  const url = `${API_BASE}/canvases/conversations/${conversationId}?_=${Date.now()}`;
  const res = await apiFetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to get conversation");
  return res.json();
}

export async function deleteConversation(
  canvasId: string,
  conversationId: string
): Promise<void> {
  const res = await apiFetch(
    `${API_BASE}/canvases/${canvasId}/conversations/${conversationId}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error("Failed to delete conversation");
}

export async function deleteConversationById(
  conversationId: string
): Promise<void> {
  const res = await apiFetch(
    `${API_BASE}/canvases/conversations/${conversationId}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error("Failed to delete conversation");
}

export async function inspectTool(
  code: string,
  dependencies?: string[]
): Promise<ToolInspectResponse> {
  const res = await apiFetch(`${API_BASE}/tools/inspect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, dependencies: dependencies ?? [] }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Failed to inspect tool" }));
    throw new Error(error.detail || "Failed to inspect tool");
  }
  return res.json();
}

export async function testTool(
  code: string,
  args: Record<string, string>,
  dependencies?: string[]
): Promise<ToolTestResponse> {
  const res = await apiFetch(`${API_BASE}/tools/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, args, dependencies: dependencies ?? [] }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Failed to test tool" }));
    throw new Error(error.detail || "Failed to test tool");
  }
  return res.json();
}

export async function listAgentDocuments(
  canvasId: string,
  agentId: string
): Promise<AgentDocument[]> {
  const res = await apiFetch(`${API_BASE}/canvases/${canvasId}/agents/${agentId}/documents`);
  if (!res.ok) throw new Error("Failed to list agent documents");
  return res.json();
}

export async function uploadAgentDocument(
  canvasId: string,
  agentId: string,
  file: File
): Promise<AgentDocument> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await apiFetch(
    `${API_BASE}/canvases/${canvasId}/agents/${agentId}/documents`,
    {
      method: "POST",
      body: formData,
    }
  );
  if (!res.ok) throw new Error("Failed to upload agent document");
  return res.json();
}

export async function deleteAgentDocument(
  canvasId: string,
  agentId: string,
  documentId: string
): Promise<void> {
  const res = await apiFetch(
    `${API_BASE}/canvases/${canvasId}/agents/${agentId}/documents/${documentId}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error("Failed to delete agent document");
}

export async function exportConversationZip(
  canvasId: string,
  conversationId: string
): Promise<Blob> {
  const res = await apiFetch(
    `${API_BASE}/canvases/${canvasId}/conversations/${conversationId}/export`
  );
  if (!res.ok) throw new Error("Failed to export conversation ZIP");
  return res.blob();
}

export async function importConversationZip(
  canvasId: string,
  file: File
): Promise<Conversation> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await apiFetch(
    `${API_BASE}/canvases/${canvasId}/conversations/import`,
    {
      method: "POST",
      body: formData,
    }
  );
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Failed to import conversation" }));
    throw new Error(error.detail || "Failed to import conversation");
  }
  return res.json();
}

export async function getActiveRun(
  conversationId: string
): Promise<ActiveRunResponse | null> {
  const res = await apiFetch(`${API_BASE}/conversations/${conversationId}/runs/active`);
  if (!res.ok) throw new Error("Failed to get active run");
  return res.json();
}

export async function getRunEventsAfter(
  runId: string,
  afterSequence: number
): Promise<ExecutionEvent[]> {
  const params = new URLSearchParams({ after_sequence: String(afterSequence) });
  const res = await apiFetch(`${API_BASE}/runs/${runId}/events?${params.toString()}`);
  if (!res.ok) throw new Error("Failed to get run events");
  return res.json();
}

export async function abortRun(runId: string): Promise<{ run_id: string; status: string }> {
  const res = await apiFetch(`${API_BASE}/runs/${runId}/abort`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to abort run");
  return res.json();
}

export async function submitInterruptResponse(
  runId: string,
  requestId: string,
  responseType: "human_input_response" | "tool_approval_response",
  data: Record<string, unknown>
): Promise<{ ok: boolean; request_id: string }> {
  const res = await apiFetch(`${API_BASE}/runs/${runId}/interrupt-response`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id: requestId, type: responseType, ...data }),
  });
  if (!res.ok) throw new Error("Failed to submit interrupt response");
  return res.json();
}
