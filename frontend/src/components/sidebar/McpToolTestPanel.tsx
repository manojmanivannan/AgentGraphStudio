import { useRef, useState, useEffect, useCallback } from "react";
import { Loader2 } from "lucide-react";
import {
  callMcpTool,
  inspectMcpTool,
  probeMcpTool,
} from "@/lib/api";
import type {
  McpInspectTool,
  McpToolCallBlock,
  McpToolGrantData,
  ToolTestResponse,
} from "@/types";

/**
 * Test panel for MCP-backed tool nodes (#135, spec §6.4): two stages —
 * (1) connection probe (init + tools/list + latency over the shared probe
 * path), (2) a live remote `tools/call` with schema-driven argument fields
 * built from the server-provided input schema. The call never throws;
 * in-band isError results render as errors, distinct from success output.
 * The credential override field follows the provider convention (blank →
 * stored credential, #131).
 */

type PanelState = "idle" | "probing" | "probed" | "testing";

interface SchemaProp {
  type?: string;
  description?: string;
}

function coerceArg(prop: SchemaProp, raw: string, isCheckbox: boolean): unknown {
  if (isCheckbox) return raw === "true";
  if (!raw) return "";
  const t = (prop.type ?? "").toLowerCase();
  if (t === "integer" || t === "number") {
    const n = Number(raw);
    return Number.isFinite(n) ? n : raw;
  }
  if (t === "array" || t === "object") {
    try {
      return JSON.parse(raw);
    } catch {
      return raw;
    }
  }
  return raw;
}

function isBooleanProp(prop: SchemaProp): boolean {
  return (prop.type ?? "").toLowerCase() === "boolean";
}

function PropField({
  name,
  prop,
  required,
  value,
  onChange,
}: {
  name: string;
  prop: SchemaProp;
  required: boolean;
  value: string;
  onChange: (v: string) => void;
}) {
  const typeHint = prop.type ?? "any";
  if (isBooleanProp(prop)) {
    return (
      <div className="flex items-center gap-2" title={prop.description ?? undefined}>
        <label className="text-[13px] text-[var(--color-text-secondary)] font-medium min-w-[60px]">
          {name}
          {required && <span className="text-[var(--color-danger)] ml-0.5">*</span>}
          <span className="text-[var(--color-text-tertiary)] ml-1 text-[12px]">boolean</span>
        </label>
        <input
          type="checkbox"
          checked={value === "true"}
          onChange={(e) => onChange(e.target.checked ? "true" : "false")}
          data-testid={`mcp-test-arg-${name}`}
          className="rounded border-[var(--color-border-default)] text-[var(--color-info)] focus:ring-[var(--color-info)] bg-[var(--color-base)]"
        />
      </div>
    );
  }
  const inputType =
    typeHint === "integer" || typeHint === "number"
      ? "number"
      : typeHint === "array" || typeHint === "object"
        ? undefined
        : "text";
  const common = {
    "data-testid": `mcp-test-arg-${name}`,
    value,
    onChange: (
      e: React.ChangeEvent<HTMLInputElement & HTMLTextAreaElement>
    ) => onChange(e.target.value),
    className: "input-base w-full text-[12px] font-[var(--font-mono)]",
    placeholder: prop.description || typeHint,
  };
  return (
    <div className="flex items-center gap-2" title={prop.description ?? undefined}>
      <label className="text-[13px] text-[var(--color-text-secondary)] font-medium min-w-[60px]">
        {name}
        {required && <span className="text-[var(--color-danger)] ml-0.5">*</span>}
        <span className="text-[var(--color-text-tertiary)] ml-1 text-[12px]">{typeHint}</span>
      </label>
      {inputType === undefined ? (
        <textarea rows={2} {...common} />
      ) : (
        <input type={inputType} {...common} />
      )}
    </div>
  );
}

function BlockView({ block }: { block: McpToolCallBlock }) {
  if (block.type === "text" && block.text != null) {
    return <div className="whitespace-pre-wrap break-all">{block.text}</div>;
  }
  return (
    <div className="text-[var(--color-text-tertiary)] italic">
      {block.placeholder ?? `[${block.type} output]`}
    </div>
  );
}

export function McpToolTestPanel({
  serverId,
  serverName,
  tools,
}: {
  serverId: string | null;
  serverName: string | null;
  tools: McpToolGrantData[];
}) {
  const [state, setState] = useState<PanelState>("idle");
  const [toolName, setToolName] = useState(tools[0]?.name ?? "");
  const [probe, setProbe] = useState<ToolTestResponse | null>(null);
  const [schema, setSchema] = useState<McpInspectTool | null>(null);
  const [argValues, setArgValues] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ToolTestResponse | null>(null);
  const [credential, setCredential] = useState("");
  const [panelError, setPanelError] = useState<string | null>(null);
  // Whether a successful probe is still valid — a successful "Test
  // connection" turns schema inspection on for tool switches.
  const probeOkRef = useRef(false);

  // Server change (or initial mount): full reset — the probe is per-server.
  useEffect(() => {
    setProbe(null);
    probeOkRef.current = false;
    setSchema(null);
    setArgValues({});
    setResult(null);
    setPanelError(null);
    setState("idle");
    setToolName(tools[0]?.name ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverId]);

  // Tool switch: while the connection probe is still valid, re-inspect just
  // the schema — the argument fields are per-tool; the probe result stays.
  useEffect(() => {
    setSchema(null);
    setArgValues({});
    setResult(null);
    setPanelError(null);
    if (!serverId || !toolName || !probeOkRef.current) return;
    let cancelled = false;
    (async () => {
      try {
        const inspected = await inspectMcpTool(serverId, toolName);
        if (cancelled) return;
        if (inspected.ok && inspected.tool) {
          setSchema(inspected.tool);
          const props = ((inspected.tool.input_schema as Record<string, unknown>).properties ?? {}) as Record<string, SchemaProp>;
          setArgValues(Object.fromEntries(Object.keys(props).map((k) => [k, ""])));
          setState("probed");
        } else {
          setPanelError(inspected.detail || "Tool not found on this server.");
        }
      } catch (e) {
        if (!cancelled) {
          setPanelError((e as Error).message || "Failed to inspect the tool schema");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toolName]);

  const handleReset = () => {
    probeOkRef.current = false;
    setProbe(null);
    setSchema(null);
    setArgValues({});
    setResult(null);
    setPanelError(null);
    setState("idle");
  };

  const handleProbe = useCallback(async () => {
    if (!serverId) return;
    setState("probing");
    setPanelError(null);
    setResult(null);
    setSchema(null);
    setProbe(null);
    probeOkRef.current = false;
    try {
      const res = await probeMcpTool(serverId, credential || undefined);
      probeOkRef.current = !!res.ok;
      setProbe(res);
      if (res.ok) {
        const inspected = await inspectMcpTool(serverId, toolName || null);
        if (inspected.ok && inspected.tool) {
          setSchema(inspected.tool);
          const props = ((inspected.tool.input_schema as Record<string,unknown>).properties ?? {}) as Record<string, SchemaProp>;
          setArgValues(
            Object.fromEntries(Object.keys(props).map((k) => [k, ""]))
          );
          setState("probed");
        } else {
          setSchema(null);
          setPanelError(inspected.detail || "Tool not found on this server.");
          setState("probed");
        }
      } else {
        setState("probed");
      }
    } catch (e) {
      setPanelError((e as Error).message || "Probe failed");
      setState("probed");
    }
  }, [serverId, toolName, credential]);

  const handleRun = async () => {
    if (!serverId || !schema) return;
    setState("testing");
    setPanelError(null);
    try {
      const props = ((schema.input_schema as Record<string, unknown>).properties ?? {}) as Record<string, SchemaProp>;
      const args: Record<string, unknown> = {};
      for (const [name, prop] of Object.entries(props)) {
        const raw = argValues[name];
        if (isBooleanProp(prop)) {
          args[name] = raw === "true";
        } else if (raw !== undefined && raw !== "") {
          args[name] = coerceArg(prop, raw, false);
        }
      }
      const res = await callMcpTool(serverId, toolName, args, credential || undefined);
      setResult(res);
    } catch (e) {
      // The backend never turns MCP failures into 5xx, but a transport-level
      // failure still surfaces here — show it as the structured error state.
      setResult({
        kind: "mcp",
        stage: "call",
        ok: false,
        is_error: false,
        success: false,
        blocks: [],
        detail: (e as Error).message || "Call failed",
        classification: "connection_failure",
      });
    } finally {
      setState("probed");
    }
  };

  if (!serverId || tools.length === 0) {
    return (
      <p className="text-[12px] text-[var(--color-text-tertiary)] italic">
        Attach an MCP server and enable a tool to test it.
      </p>
    );
  }

  const argsReady = state === "probed" && !!schema;
  const runDisabled = state === "testing";
  const probeResult = probe;

  return (
    <div className="space-y-2">
      <div>
        <label className="block text-[13px] font-semibold text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-[0.06em]">
          Tool
        </label>
        <select
          data-testid="mcp-test-tool-select"
          value={toolName}
          onChange={(e) => setToolName(e.target.value)}
          className="input-base w-full"
        >
          {tools.map((t) => (
            <option key={t.name} value={t.name}>
              {t.name}
            </option>
          ))}
        </select>
      </div>

      {state === "probing" && (
        <div className="flex items-center justify-center py-3 gap-2 text-[var(--color-text-tertiary)]">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          <span className="text-[12px]">Probing server...</span>
        </div>
      )}

      {state === "testing" && (
        <div className="flex items-center justify-center py-3 gap-2 text-[var(--color-text-tertiary)]">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          <span className="text-[12px]">Calling remote tool...</span>
        </div>
      )}

      {(state === "idle" || state === "probed") && (
        <button
          onClick={handleProbe}
          data-testid="mcp-test-connection-button"
          className="btn-secondary w-full text-[12px]"
          disabled={state === "probed"}
        >
          Test connection
        </button>
      )}

      {probeResult && (
        <div
          data-testid="mcp-test-probe-result"
          data-ok={String(!!probeResult.ok)}
          className={`rounded-lg p-3 text-[12px] ${
            probeResult.ok
              ? "bg-[var(--color-success-subtle)] border border-[var(--color-success)]/20"
              : "bg-[var(--color-danger-subtle)] border border-[var(--color-danger)]/20"
          }`}
        >
          <div className="flex items-center justify-between mb-1">
            <span
              className={`text-[12px] font-semibold uppercase tracking-[0.06em] ${
                probeResult.ok ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"
              }`}
            >
              {probeResult.ok ? "CONNECTED" : "CONNECTION FAILED"}
            </span>
            <span className="text-[12px] text-[var(--color-text-tertiary)]">
              {probeResult.latency_ms} ms
            </span>
          </div>
          <div className="text-[var(--color-text-secondary)]">
            {probeResult.ok
              ? `${probeResult.server_name ?? serverName ?? "server"} — ${probeResult.tool_count ?? 0} tools`
              : probeResult.detail}
          </div>
        </div>
      )}

      {panelError && !schema && (
        <div
          data-testid="mcp-test-panel-error"
          className="rounded-lg p-3 text-[12px] bg-[var(--color-danger-subtle)] border border-[var(--color-danger)]/20 text-[var(--color-danger)]"
        >
          {panelError}
        </div>
      )}

      {schema && (
        <div className="space-y-1.5">
          <span className="text-[12px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-[0.06em]">
            Arguments
          </span>
          {(() => {
            const inputSchema = schema.input_schema as Record<string, unknown>;
            const props = (inputSchema.properties ?? {}) as Record<string, SchemaProp>;
            const required = (inputSchema.required ?? []) as string[];
            const propEntries = Object.entries(props);
            if (propEntries.length === 0) {
              return (
                <p className="text-[13px] text-[var(--color-text-tertiary)] italic">
                  No arguments required
                </p>
              );
            }
            return propEntries.map(([name, prop]) => (
              <PropField
                key={name}
                name={name}
                prop={prop}
                required={required.includes(name)}
                value={argValues[name] ?? ""}
                onChange={(v) => setArgValues((prev) => ({ ...prev, [name]: v }))}
              />
            ));
          })()}
        </div>
      )}

      <div>
        <label className="block text-[13px] font-semibold text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-[0.06em]">
          Credential Override
        </label>
        <input
          type="password"
          data-testid="mcp-test-credential"
          value={credential}
          onChange={(e) => setCredential(e.target.value)}
          className="input-base w-full"
          placeholder="••••••••"
          autoComplete="off"
        />
        <p className="text-[11px] text-[var(--color-text-tertiary)] mt-0.5">
          Stored credential used if blank
        </p>
      </div>

      {argsReady && (
        <div className="flex gap-2">
          <button
            onClick={handleRun}
            data-testid="mcp-test-run-button"
            className="btn-secondary flex-1 text-[12px]"
            disabled={runDisabled}
          >
            Run Tool
          </button>
          <button onClick={handleReset} className="btn-ghost text-[13px] px-2 py-1">
            Reset
          </button>
        </div>
      )}

      {result && (
        <div
          data-testid="mcp-test-result"
          data-status={result.success ? "success" : "error"}
          className={`rounded-lg p-3 text-[12px] font-[var(--font-mono)] whitespace-pre-wrap break-all max-h-[200px] overflow-auto ${
            result.success
              ? "bg-[var(--color-success-subtle)] border border-[var(--color-success)]/20 text-[var(--color-text-primary)]"
              : "bg-[var(--color-danger-subtle)] border border-[var(--color-danger)]/20 text-[var(--color-text-primary)]"
          }`}
        >
          <div className="flex items-center justify-between mb-1">
            <span
              className={`text-[12px] font-semibold uppercase tracking-[0.06em] ${
                result.success ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"
              }`}
            >
              {result.success
                ? "Output"
                : result.ok && result.is_error
                  ? "Error result (isError)"
                  : "Error"}
            </span>
            <span className="text-[12px] text-[var(--color-text-tertiary)]">
              {result.latency_ms} ms
            </span>
          </div>
          {result.success || (result.ok && result.is_error) ? (
            (result.blocks ?? []).length === 0 ? (
              <span className="italic text-[var(--color-text-tertiary)]">No output blocks</span>
            ) : (
              <div className="space-y-1">
                {(result.blocks ?? []).map((block, i) => (
                  <BlockView key={i} block={block} />
                ))}
              </div>
            )
          ) : (
            <div>
              {result.detail}
              {result.classification && (
                <div className="text-[var(--color-text-tertiary)] mt-1">
                  ({result.classification})
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}