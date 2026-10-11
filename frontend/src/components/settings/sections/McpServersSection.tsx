import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Check, Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import {
  createMcpServer,
  deleteMcpServer,
  listMcpServers,
  updateMcpServer,
} from "@/lib/api";
import type { McpServer, McpServerForm } from "@/types";

type Feedback =
  | { kind: "success"; message: string }
  | { kind: "error"; message: string }
  | null;

const inputClass =
  "px-3 py-2 bg-[var(--color-inset)] border border-[var(--color-border-default)] rounded-lg text-sm outline-none focus:border-[var(--color-accent)] transition-colors text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)]";

interface EditorState {
  id: string | null;
  form: McpServerForm;
  /** "" (no typing yet / blank) means: null on the wire → keep nothing-or-stored. */
  credentialValue: string;
  /** Edit-time "wipe the stored credential" option (sends ""). */
  clearStored: boolean;
  saving: boolean;
}

const EMPTY_FORM: McpServerForm = {
  name: "",
  url: "",
  credential_header: "Authorization",
};

function CredentialBadge({ server }: { server: McpServer }) {
  return (
    <span className="text-xs text-[var(--color-text-tertiary)]">
      {server.credential_header ? `${server.credential_header} · ` : ""}
      {server.credential_set
        ? `credential stored ${server.credential_preview ?? "••••"}`
        : "no credential"}
    </span>
  );
}

export function McpServersSection() {
  const [servers, setServers] = useState<McpServer[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const loaded = await listMcpServers();
      setServers(loaded);
      setLoadError(null);
    } catch (err: any) {
      setLoadError(err?.message || "Failed to load MCP servers.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openCreate = () => {
    setFeedback(null);
    setEditor({
      id: null,
      form: { ...EMPTY_FORM },
      credentialValue: "",
      clearStored: false,
      saving: false,
    });
  };

  const openEdit = (server: McpServer) => {
    setFeedback(null);
    setEditor({
      id: server.id,
      form: {
        name: server.name,
        url: server.url,
        credential_header: server.credential_header ?? "Authorization",
      },
      credentialValue: "",
      clearStored: false,
      saving: false,
    });
  };

  const closeEditor = () => setEditor(null);

  const save = async () => {
    if (!editor) return;
    setEditor({ ...editor, saving: true });
    setFeedback(null);
    try {
      if (editor.id) {
        await updateMcpServer(
          editor.id,
          editor.form,
          editor.clearStored ? "" : editor.credentialValue || null
        );
        setFeedback({ kind: "success", message: "MCP server saved." });
      } else {
        await createMcpServer(editor.form, editor.credentialValue || null);
        setFeedback({ kind: "success", message: "MCP server saved." });
      }
      setEditor(null);
      await load();
    } catch (err: any) {
      setEditor((prev) => (prev ? { ...prev, saving: false } : prev));
      setFeedback({
        kind: "error",
        message: err?.message || "Failed to save MCP server.",
      });
    }
  };

  const remove = async (server: McpServer) => {
    setDeletingId(server.id);
    setFeedback(null);
    try {
      await deleteMcpServer(server.id);
      await load();
    } catch (err: any) {
      setFeedback({
        kind: "error",
        message: err?.message || "Failed to delete MCP server.",
      });
    } finally {
      setDeletingId(null);
    }
  };

  if (servers === null && !loadError && !editor) {
    return (
      <p className="text-sm text-[var(--color-text-tertiary)]">
        Loading MCP servers…
      </p>
    );
  }

  if (servers === null && loadError) {
    return (
      <p role="alert" className="text-sm text-[var(--color-danger)]">
        {loadError}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {feedback && (
        <div
          role="alert"
          className={`flex items-start gap-2 p-3 rounded-lg border text-xs ${
            feedback.kind === "success"
              ? "bg-[var(--color-success-subtle)] border-[var(--color-success)]/30 text-[var(--color-success)]"
              : "bg-[var(--color-danger-subtle)] border-[var(--color-danger)]/30 text-[var(--color-danger)]"
          }`}
        >
          {feedback.kind === "success" ? (
            <Check className="w-4 h-4 shrink-0 mt-0.5" />
          ) : (
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          )}
          <p>{feedback.message}</p>
        </div>
      )}

      {servers !== null && servers.length === 0 && !editor && (
        <p className="text-sm text-[var(--color-text-tertiary)]">
          No MCP servers yet. Add an external MCP endpoint to make its tools
          available to your agents.
        </p>
      )}

      {servers !== null && !editor && (
        <ul className="flex flex-col gap-2">
          {servers.map((server) => (
            <li
              key={server.id}
              data-testid={`mcp-server-row-${server.name}`}
              className="flex items-start justify-between gap-3 p-3 rounded-xl border border-[var(--color-border-default)]"
            >
              <div className="flex flex-col gap-1 min-w-0">
                <span className="text-sm font-medium text-[var(--color-text-primary)]">
                  {server.name}
                </span>
                <span className="text-xs text-[var(--color-text-secondary)] break-all">
                  {server.url}
                </span>
                <CredentialBadge server={server} />
                {server.url_warning && (
                  <span className="mcp-url-warning text-xs text-[var(--color-warning)]">
                    {server.url_warning}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  type="button"
                  onClick={() => openEdit(server)}
                  aria-label={`Edit ${server.name}`}
                  className="p-2 rounded-lg text-[var(--color-text-secondary)] hover:bg-[var(--color-elevated)] transition-colors"
                >
                  <Pencil className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={() => remove(server)}
                  disabled={deletingId === server.id}
                  aria-label={`Delete ${server.name}`}
                  className="p-2 rounded-lg text-[var(--color-danger)] hover:bg-[var(--color-elevated)] transition-colors disabled:opacity-50"
                >
                  {deletingId === server.id ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Trash2 className="w-4 h-4" />
                  )}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {servers !== null && !editor && (
        <div className="flex items-center gap-2 pt-2 border-t border-[var(--color-border-subtle)]">
          <button
            type="button"
            onClick={openCreate}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-[var(--color-border-default)] text-sm text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add server
          </button>
        </div>
      )}

      {editor && (
        <form
          className="flex flex-col gap-4 p-3 rounded-xl border border-[var(--color-border-default)]"
          onSubmit={(e) => {
            e.preventDefault();
            save();
          }}
        >
          <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">
            {editor.id ? "Edit MCP server" : "New MCP server"}
          </h2>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="mcp-server-name"
              className="text-xs font-medium text-[var(--color-text-secondary)]"
            >
              Name
            </label>
            <input
              id="mcp-server-name"
              type="text"
              value={editor.form.name}
              onChange={(e) =>
                setEditor({
                  ...editor,
                  form: { ...editor.form, name: e.target.value },
                })
              }
              className={inputClass}
              required
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="mcp-server-url"
              className="text-xs font-medium text-[var(--color-text-secondary)]"
            >
              URL
            </label>
            <input
              id="mcp-server-url"
              type="text"
              value={editor.form.url}
              onChange={(e) =>
                setEditor({
                  ...editor,
                  form: { ...editor.form, url: e.target.value },
                })
              }
              className={inputClass}
              placeholder="https://mcp.example.com/mcp"
              required
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="mcp-server-header"
              className="text-xs font-medium text-[var(--color-text-secondary)]"
            >
              Credential header
            </label>
            <input
              id="mcp-server-header"
              type="text"
              value={editor.form.credential_header ?? ""}
              onChange={(e) =>
                setEditor({
                  ...editor,
                  form: { ...editor.form, credential_header: e.target.value },
                })
              }
              className={inputClass}
              placeholder="Authorization"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="mcp-server-credential"
              className="text-xs font-medium text-[var(--color-text-secondary)]"
            >
              Credential value
            </label>
            <input
              id="mcp-server-credential"
              type="password"
              autoComplete="off"
              value={editor.credentialValue}
              onChange={(e) =>
                setEditor({ ...editor, credentialValue: e.target.value })
              }
              className={inputClass}
              placeholder={editor.id ? "••••••••" : "Bearer sk-…"}
            />
            <span className="text-[13px] text-[var(--color-text-tertiary)]">
              {editor.id
                ? editor.clearStored
                  ? "The stored credential will be cleared on save."
                  : "Leave blank to keep the stored credential."
                : "Optional header value, e.g. a bearer token."}
            </span>
            {editor.id && (
              <label className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
                <input
                  type="checkbox"
                  checked={editor.clearStored}
                  onChange={(e) =>
                    setEditor({ ...editor, clearStored: e.target.checked })
                  }
                />
                Clear stored credential
              </label>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="submit"
              disabled={editor.saving}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {editor.saving && <Loader2 className="w-4 h-4 animate-spin" />}
              Save
            </button>
            <button
              type="button"
              onClick={closeEditor}
              className="px-3 py-2 rounded-lg border border-[var(--color-border-default)] text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-elevated)] transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  );
}