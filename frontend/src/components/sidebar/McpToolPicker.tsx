import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useCanvasStore } from "@/store/canvasStore";
import { useSettingsModalStore } from "@/store/settingsModalStore";
import { fetchMcpServerCatalog, listMcpServers } from "@/lib/api";
import type { McpServer, McpServerCatalog, ToolNodeData } from "@/types";

/**
 * The MCP-backed Tool Node editor body (#134, spec §6.2 — Variant A, one
 * scrolling picker): server chip → registered-servers picker, then the
 * live-catalog checklist with per-row enable/approval/schema rows, NEW
 * badges, and the excluded block for vanished tools.
 *
 * There is no caching anywhere (decision #126): every open and every Refresh
 * rides the shared catalog endpoint's short-lived probe connection, and an
 * unreachable server shows an honest error + Retry — never stale tools.
 */

type CatalogState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; catalog: McpServerCatalog; newNames: Set<string> };

/** How much of a description shows before truncation in a checklist row. */
const DESCRIPTION_MAX = 72;

function truncate(text: string, max = DESCRIPTION_MAX): string {
  return text.length > max ? text.slice(0, max - 1) + "…" : text;
}

export function McpToolPicker({
  nodeId,
  children,
}: {
  nodeId: string;
  /** Rendered between the server chip and the checklist — the editor's Name
   * field in the §6.2 order (chip → name → checklist). */
  children?: ReactNode;
}) {
  const nodes = useCanvasStore((s) => s.nodes);
  const setNodes = useCanvasStore((s) => s.setNodes);
  const openSettings = useSettingsModalStore((s) => s.openSettings);
  const node = nodes.find((n) => n.id === nodeId);
  const data = (node?.data ?? {}) as Partial<ToolNodeData>;

  const [servers, setServers] = useState<McpServer[]>([]);
  const [showPicker, setShowPicker] = useState(false);
  const [catalogState, setCatalogState] = useState<CatalogState>({
    status: "loading",
  });
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  const serverId = data.mcpServerId ?? null;
  const server = servers.find((s) => s.id === serverId) ?? null;

  // The registered-servers list (for the chip label and the picker).
  useEffect(() => {
    let cancelled = false;
    listMcpServers()
      .then((loaded) => {
        if (!cancelled) setServers(loaded);
      })
      .catch(() => {
        /* the picker itself will surface errors on selection */
      });
    return () => {
      cancelled = true;
    };
  }, [showPicker]);

  const diffAndMergeSeen = useCallback(
    (catalog: McpServerCatalog) => {
      // The NEW diff is against the enablement *history* recorded before
      // this fetch; the fetch itself then advances the history with the
      // names it showed (names only — never a catalog snapshot).
      const seenBefore = new Set(data.mcpSeenTools ?? []);
      const newNames = new Set(
        catalog.tools
          .map((tool) => tool.name)
          .filter((name) => !seenBefore.has(name))
      );
      const merged = [...seenBefore, ...newNames];
      if (merged.length > seenBefore.size) {
        updateData({ mcpSeenTools: merged });
      }
      return newNames;
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data.mcpSeenTools]
  );

  const loadCatalog = useCallback(async () => {
    if (!serverId) return;
    setCatalogState({ status: "loading" });
    try {
      const catalog = await fetchMcpServerCatalog(serverId);
      const newNames = diffAndMergeSeen(catalog);
      setCatalogState({ status: "ready", catalog, newNames });
    } catch (err) {
      // Transport-level failure (dangling server reference, network...).
      // Structured unreachable-server responses arrive as a normal ok=false
      // payload, never a rejection.
      const message =
        err instanceof Error ? err.message : "Failed to fetch the tool catalog.";
      setCatalogState({ status: "error", message });
    }
  }, [serverId, diffAndMergeSeen]);

  useEffect(() => {
    loadCatalog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverId, refreshTick]);

  function updateData(patch: Partial<ToolNodeData>) {
    const currentNodes = useCanvasStore.getState().nodes;
    setNodes(
      currentNodes.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, ...patch } } : n
      )
    );
  }

  function selectServer(server: McpServer) {
    // Selecting (or switching) a server resets the tool selection — the old
    // grant belonged to a different server, and MCP nodes carry no code.
    updateData({ mcpServerId: server.id, mcpTools: [], code: "" });
    setShowPicker(false);
  }

  function toggleEnabled(toolName: string, enabled: boolean) {
    const grants = (data.mcpTools ?? []).filter((g) => g.name !== toolName);
    if (enabled) {
      // Every enable action defaults requires_approval = true (§5.3).
      grants.push({ name: toolName, requiresApproval: true });
    }
    updateData({ mcpTools: grants });
  }

  function toggleApproval(toolName: string, requiresApproval: boolean) {
    updateData({
      mcpTools: (data.mcpTools ?? []).map((grant) =>
        grant.name === toolName ? { ...grant, requiresApproval } : grant
      ),
    });
  }

  function dropGrant(toolName: string) {
    updateData({
      mcpTools: (data.mcpTools ?? []).filter((g) => g.name !== toolName),
    });
  }

  const grants = useMemo(
    () => new Map((data.mcpTools ?? []).map((grant) => [grant.name, grant])),
    [data.mcpTools]
  );

  const catalog =
    catalogState.status === "ready" ? catalogState.catalog : null;
  const catalogNames = useMemo(
    () => new Set((catalog?.tools ?? []).map((tool) => tool.name)),
    [catalog]
  );
  const excluded = (data.mcpTools ?? []).filter(
    (grant) => !catalogNames.has(grant.name)
  );

  if (!node) return null;

  // A granted server that is no longer registered: honest error state —
  // the grant stays intact (no silent loss) but there is no catalog to show
  // and nothing stale to display.
  const isUnregistered = serverId !== null && server === null;

  return (
    <div className="space-y-2" data-testid="mcp-tool-picker">
      {/* ── Server chip / attach affordance ───────────────────────────── */}
      {serverId ? (
        isUnregistered ? (
          <button
            type="button"
            data-testid="mcp-server-chip"
            onClick={() => setShowPicker(true)}
            className="w-full flex flex-col items-start gap-0.5 p-2.5 rounded-lg border border-[var(--color-danger)]/40 bg-[var(--color-danger-subtle)] transition-colors text-left cursor-pointer"
          >
            <span className="text-[12px] font-semibold text-[var(--color-danger)]">
              Server no longer registered
            </span>
            <span className="text-[11px] text-[var(--color-text-tertiary)] break-all">
              Unknown server reference ({serverId})
            </span>
          </button>
        ) : (
          <button
            type="button"
            data-testid="mcp-server-chip"
            onClick={() => setShowPicker(true)}
            className="w-full flex flex-col items-start gap-0.5 p-2.5 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-inset)] hover:bg-[var(--color-elevated)] transition-colors text-left cursor-pointer"
          >
            <span className="text-[12px] font-semibold text-[var(--color-text-primary)]">
              {server!.name}
            </span>
            <span className="text-[11px] text-[var(--color-text-tertiary)] break-all">
              {server!.url}
            </span>
          </button>
        )
      ) : (
        <button
          type="button"
          data-testid="mcp-attach-server"
          onClick={() => setShowPicker(true)}
          className="btn-secondary w-full text-[12px]"
        >
          Attach MCP server
        </button>
      )}

      {/* The registered-servers picker (server management lives in Settings). */}
      {showPicker && (
        <div
          data-testid="mcp-server-picker"
          className="flex flex-col gap-1 p-2.5 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-surface)]"
        >
          <div className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--color-text-tertiary)]">
            Registered servers
          </div>
          {servers.length === 0 && (
            <p className="text-[12px] text-[var(--color-text-tertiary)]">
              No MCP servers registered yet.
            </p>
          )}
          {servers.map((candidate) => (
            <button
              key={candidate.id}
              type="button"
              data-testid={`mcp-select-server-${candidate.name}`}
              onClick={() => selectServer(candidate)}
              className="flex flex-col items-start gap-0.5 p-2 rounded-lg border border-[var(--color-border-subtle)] hover:bg-[var(--color-elevated)] transition-colors text-left cursor-pointer"
            >
              <span className="text-[12px] font-medium text-[var(--color-text-primary)]">
                {candidate.name}
              </span>
              <span className="text-[11px] text-[var(--color-text-tertiary)] break-all">
                {candidate.url}
              </span>
            </button>
          ))}
          <button
            type="button"
            data-testid="mcp-manage-servers"
            onClick={() => openSettings("mcp-servers")}
            className="text-[12px] text-[var(--color-info)] underline cursor-pointer self-start"
          >
            Manage servers
          </button>
        </div>
      )}
      {!showPicker && serverId && (
        <button
          type="button"
          data-testid="mcp-manage-servers"
          onClick={() => openSettings("mcp-servers")}
          className="text-[12px] text-[var(--color-info)] underline cursor-pointer self-start"
        >
          Manage servers
        </button>
      )}

      {children}

      {/* ── Excluded — no longer on ⟨server⟩ (#119 no-silent-loss) ─────── */}
      {excluded.length > 0 && (
        <div
          data-testid="mcp-excluded-block"
          className="flex flex-col gap-1.5 p-2.5 rounded-lg border border-[var(--color-warning)]/40 bg-[var(--color-warning-subtle)]"
        >
          <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--color-warning)]">
            Excluded — no longer on {server?.name ?? "the granted server"}
          </span>
          {excluded.map((grant) => (
            <div
              key={grant.name}
              data-testid={`mcp-excluded-${grant.name}`}
              className="flex items-center justify-between gap-2"
            >
              <span className="text-[12px] text-[var(--color-text-secondary)] line-through">
                {grant.name}
              </span>
              <button
                type="button"
                data-testid={`mcp-drop-${grant.name}`}
                onClick={() => dropGrant(grant.name)}
                className="px-2 py-0.5 text-[11px] rounded border border-[var(--color-border-default)] text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] transition-colors cursor-pointer"
              >
                Drop
              </button>
            </div>
          ))}
        </div>
      )}

      {/* ── Live catalog checklist ─────────────────────────────────────── */}
      {catalogState.status === "loading" && (
        <div
          data-testid="mcp-catalog-loading"
          className="text-[12px] text-[var(--color-text-tertiary)] py-2"
        >
          Fetching tools…
        </div>
      )}

      {(catalogState.status === "error" || isUnregistered) && (
        <div
          data-testid="mcp-catalog-error"
          className="rounded-lg p-2.5 text-[12px] bg-[var(--color-danger-subtle)] border border-[var(--color-danger)]/20 text-[var(--color-danger)]"
        >
          <p>
            {isUnregistered
              ? "This MCP server is no longer registered. Manage servers in Settings."
              : !serverId
                ? "No server granted."
                : catalogState.status === "error"
                  ? catalogState.message
                  : "Failed to fetch the tool catalog."}
          </p>
          {serverId && !isUnregistered && catalogState.status === "error" && (
            <button
              type="button"
              data-testid="mcp-retry"
              onClick={() => setRefreshTick((t) => t + 1)}
              className="btn-ghost mt-1.5 text-[12px]"
            >
              Retry
            </button>
          )}
        </div>
      )}

      {catalogState.status === "ready" && catalog && (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-[0.06em]">
              Server Tools ({catalog.tools.length})
            </span>
            <button
              type="button"
              data-testid="mcp-refresh"
              onClick={() => setRefreshTick((t) => t + 1)}
              className="px-2 py-1 text-[11px] rounded border border-[var(--color-border-default)] text-[var(--color-text-secondary)] hover:bg-[var(--color-elevated)] transition-colors cursor-pointer"
            >
              Refresh
            </button>
          </div>

          <input
            type="text"
            data-testid="mcp-filter"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter tools…"
            className="input-base w-full text-[12px]"
          />

          <ul
            data-testid="mcp-tools-list"
            className="flex flex-col gap-1 max-h-[280px] overflow-y-auto pr-0.5"
          >
            {catalog.tools
              .filter((tool) => {
                const query = filter.trim().toLowerCase();
                if (!query) return true;
                return (
                  tool.name.toLowerCase().includes(query) ||
                  (tool.description ?? "").toLowerCase().includes(query)
                );
              })
              .map((tool) => {
                const grant = grants.get(tool.name);
                const enabled = !!grant;
                return (
                  <li
                    key={tool.name}
                    data-testid={`mcp-tool-row-${tool.name}`}
                    className="flex flex-col gap-1 p-2 rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-inset)]"
                  >
                    <div className="flex items-start gap-2">
                      <input
                        type="checkbox"
                        data-testid={`mcp-enable-${tool.name}`}
                        checked={enabled}
                        onChange={(e) => toggleEnabled(tool.name, e.target.checked)}
                        className="mt-0.5 rounded border-[var(--color-border-default)] bg-[var(--color-base)]"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="text-[12px] font-medium text-[var(--color-text-primary)] font-[var(--font-mono)]">
                            {tool.name}
                          </span>
                          {catalogState.newNames.has(tool.name) && (
                            <span
                              data-testid={`mcp-new-badge-${tool.name}`}
                              className="px-1 py-0.5 rounded bg-[var(--color-info-subtle)] text-[var(--color-info)] text-[10px] font-semibold uppercase"
                            >
                              NEW
                            </span>
                          )}
                        </div>
                        {tool.description && (
                          <p
                            className="text-[11px] text-[var(--color-text-tertiary)]"
                            title={tool.description}
                          >
                            {truncate(tool.description)}
                          </p>
                        )}
                      </div>
                      <button
                        type="button"
                        data-testid={`mcp-schema-toggle-${tool.name}`}
                        onClick={() =>
                          setExpanded((cur) =>
                            cur === tool.name ? null : tool.name
                          )
                        }
                        className="px-1.5 py-0.5 text-[11px] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] transition-colors cursor-pointer shrink-0"
                      >
                        {expanded === tool.name ? "Hide schema" : "Schema"}
                      </button>
                    </div>

                    {enabled && (
                      <label className="flex items-center gap-2 pl-6 cursor-pointer">
                        <input
                          type="checkbox"
                          data-testid={`mcp-approval-${tool.name}`}
                          checked={grant!.requiresApproval}
                          onChange={(e) =>
                            toggleApproval(tool.name, e.target.checked)
                          }
                          className="rounded border-[var(--color-border-default)] bg-[var(--color-base)]"
                        />
                        <span className="text-[11px] text-[var(--color-text-secondary)]">
                          Require approval
                        </span>
                      </label>
                    )}

                    {expanded === tool.name && (
                      <pre
                        data-testid={`mcp-schema-${tool.name}`}
                        className="ml-6 p-2 rounded bg-[var(--color-base)] border border-[var(--color-border-subtle)] text-[10px] font-[var(--font-mono)] whitespace-pre-wrap break-all max-h-[160px] overflow-auto text-[var(--color-text-secondary)]"
                      >
                        {JSON.stringify(tool.input_schema, null, 2)}
                      </pre>
                    )}
                  </li>
                );
              })}
          </ul>

          {catalog.tools.length === 0 && (
            <p
              data-testid="mcp-catalog-empty"
              className="text-[12px] text-[var(--color-text-tertiary)] italic"
            >
              This server exposes no tools.
            </p>
          )}
        </div>
      )}
    </div>
  );
}