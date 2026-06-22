import { useState, useEffect, useCallback } from "react";
import Editor from "@monaco-editor/react";
import { useCanvasStore } from "@/store/canvasStore";
import { useThemeStore } from "@/store/themeStore";
import { inspectTool, testTool } from "@/lib/api";
import type { ToolInspectResponse, ToolTestResponse } from "@/types";
import { InfoTooltip } from "./InfoTooltip";

type TestState = "idle" | "inspecting" | "ready" | "testing" | "success" | "error";

export function ToolEditor() {
  const selectedNodeId = useCanvasStore((s) => s.selectedNodeId);
  const nodes = useCanvasStore((s) => s.nodes);
  const setNodes = useCanvasStore((s) => s.setNodes);
  const theme = useThemeStore((s) => s.theme);
  const editorTheme = theme === "dark" ? "vs-dark" : "light";

  const selectedNode = nodes.find((n) => n.id === selectedNodeId && n.type === "tool");

  const [localName, setLocalName] = useState("");
  const [localPackages, setLocalPackages] = useState("");
  const [localCode, setLocalCode] = useState("");

  // Test tool state
  const [testState, setTestState] = useState<TestState>("idle");
  const [argumentInfo, setArgumentInfo] = useState<ToolInspectResponse["arguments"]>([]);
  const [testArgs, setTestArgs] = useState<Record<string, string>>({});
  const [testResult, setTestResult] = useState<ToolTestResponse | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  useEffect(() => {
    if (selectedNode) {
      setLocalName((selectedNode.data as any)?.name ?? "");
      setLocalPackages((selectedNode.data as any)?.packages ?? "");
      setLocalCode((selectedNode.data as any)?.code ?? "");
    }
  }, [selectedNodeId]);

  // Reset test state when code changes
  useEffect(() => {
    if (testState !== "idle") {
      setTestState("idle");
      setArgumentInfo([]);
      setTestArgs({});
      setTestResult(null);
      setTestError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localCode]);

  if (!selectedNode) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--color-text-tertiary)] text-[12px]">
        Select a tool node to edit its code
      </div>
    );
  }

  // Simple regex to extract function arguments from the code for preview
  const extractArgs = (code: string) => {
    const match = code.match(/def\s+\w+\s*\(([^)]*)\):/);
    if (!match) return [];
    return match[1]
      .split(",")
      .map((arg) => arg.trim())
      .filter((arg) => arg !== "");
  };

  const args = extractArgs(localCode);

  const updateStore = (field: string, value: string) => {
    const currentNodes = useCanvasStore.getState().nodes;
    const newNodes = currentNodes.map((n) =>
      n.id === selectedNodeId
        ? { ...n, data: { ...n.data, [field]: value } }
        : n
    );
    setNodes(newNodes);
  };

  const parsePackages = (packages: string): string[] =>
    packages
      .split(",")
      .map((p) => p.trim())
      .filter((p) => p.length > 0);

  const handleInspect = async () => {
    if (!localCode.trim()) {
      setTestError("Write some Python code first");
      setTestState("error");
      return;
    }
    setTestState("inspecting");
    setTestError(null);
    try {
      const pkgs = parsePackages(localPackages);
      const result = await inspectTool(localCode, pkgs);
      setArgumentInfo(result.arguments);
      // Initialize test args with default values
      const initialArgs: Record<string, string> = {};
      for (const arg of result.arguments) {
        initialArgs[arg.name] = arg.default_value
          ? arg.default_value.replace(/^['"]|['"]$/g, "") // strip quotes from default
          : "";
      }
      setTestArgs(initialArgs);
      setTestState("ready");
      setTestResult(null);
    } catch (e: any) {
      setTestError(e.message || "Failed to inspect tool");
      setTestState("error");
    }
  };

  const handleRunTest = async () => {
    setTestState("testing");
    setTestError(null);
    try {
      const pkgs = parsePackages(localPackages);
      const result = await testTool(localCode, testArgs, pkgs);
      setTestResult(result);
      setTestState(result.success ? "success" : "error");
    } catch (e: any) {
      setTestError(e.message || "Failed to test tool");
      setTestState("error");
    }
  };

  const handleResetTest = () => {
    setTestState("idle");
    setArgumentInfo([]);
    setTestArgs({});
    setTestResult(null);
    setTestError(null);
  };

  const getInputTypeForHint = (typeHint: string): string => {
    if (typeHint === "int" || typeHint === "float") return "number";
    if (typeHint === "bool") return "checkbox";
    if (typeHint === "list" || typeHint === "dict") return "textarea";
    return "text";
  };

  const isTesting = testState === "inspecting" || testState === "testing";

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 pb-3 border-b border-[var(--color-border-subtle)]">
        <div className="w-5 h-5 rounded-md bg-[var(--color-secondary-subtle)] flex items-center justify-center">
          <svg className="w-3 h-3 text-[var(--color-secondary)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
          </svg>
        </div>
        <h3 className="text-[13px] font-semibold text-[var(--color-text-primary)]">Tool Properties</h3>
      </div>

      <div className="flex items-center justify-between p-2.5 bg-[var(--color-secondary-surface)] border border-[var(--color-secondary)]/15 rounded-lg">
        <span className="text-[10px] font-semibold text-[var(--color-secondary)] uppercase tracking-[0.1em]">
          Inferred Arguments
        </span>
        <div className="flex gap-1">
          {args.length > 0 ? (
            args.map((arg) => (
              <span key={arg} className="px-1.5 py-0.5 bg-[var(--color-base)] border border-[var(--color-secondary)]/20 text-[var(--color-secondary)] rounded text-[10px] font-[var(--font-mono)]">
                {arg}
              </span>
            ))
          ) : (
            <span className="text-[10px] text-[var(--color-text-tertiary)] italic">None detected</span>
          )}
        </div>
      </div>

      <div>
        <label className="block text-[11px] font-semibold text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-[0.06em]">Name</label>
        <input
          type="text"
          value={localName}
          onChange={(e) => {
            setLocalName(e.target.value);
            updateStore("name", e.target.value);
          }}
          data-testid="tool-name-input"
          className="input-base w-full"
          placeholder="Tool name"
        />
      </div>

      <div>
        <label className="block text-[11px] font-semibold text-[var(--color-text-tertiary)] mb-1.5 uppercase tracking-[0.06em]">Python Packages</label>
        <input
          type="text"
          value={localPackages}
          onChange={(e) => {
            setLocalPackages(e.target.value);
            updateStore("packages", e.target.value);
          }}
          data-testid="tool-packages-input"
          className="input-base w-full"
          placeholder="e.g. pandas, requests"
        />
      </div>

      <div>
        <div className="mb-1.5 flex items-center gap-1.5">
          <label className="text-[11px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-[0.06em]">Python Code</label>
          <InfoTooltip
            testId="tool-python-code-info"
            ariaLabel="Tool python code tips"
            content="Ensure function name and tool name are same to support for conversation replay highlighting"
          />
        </div>
        <div className="border border-[var(--color-border-default)] rounded-lg overflow-hidden h-[300px]">
          <Editor
            height="300px"
            defaultLanguage="python"
            value={localCode}
            onChange={(value) => {
              setLocalCode(value ?? "");
              updateStore("code", value ?? "");
            }}
            theme={editorTheme}
            wrapperProps={{ "data-testid": "tool-code-editor" }}
            options={{
              minimap: { enabled: false },
              fontSize: 13,
              fontFamily: "JetBrains Mono, monospace",
              lineNumbers: "on",
              scrollBeyondLastLine: false,
              wordWrap: "on",
              automaticLayout: true,
              padding: { top: 8 },
              renderLineHighlight: "gutter",
              bracketPairColorization: { enabled: true },
            }}
          />
        </div>
      </div>

      {/* ── Test Tool Section ────────────────────────────────────────── */}
      <div className="pt-3 border-t border-[var(--color-border-subtle)]">
        <div className="flex items-center gap-2 mb-2">
          <svg className="w-3.5 h-3.5 text-[var(--color-secondary)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 12l2 2 4-4" />
            <circle cx="12" cy="12" r="10" />
          </svg>
          <h4 className="text-[11px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-[0.06em]">
            Test Tool
          </h4>
        </div>

        {testState === "idle" && (
          <button
            onClick={handleInspect}
            data-testid="tool-test-button"
            className="btn-secondary w-full text-[12px]"
            disabled={!localCode.trim()}
          >
            Inspect &amp; Test
          </button>
        )}

        {(testState === "inspecting" || testState === "testing") && (
          <div className="flex items-center justify-center py-3 gap-2 text-[var(--color-text-tertiary)]">
            <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.25" />
              <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            </svg>
            <span className="text-[12px]">
              {testState === "inspecting" ? "Inspecting..." : "Initializing/Running..."}
            </span>
          </div>
        )}

        {(testState === "ready" || testState === "success" || testState === "error") && (
          <div className="space-y-2">
            {/* Argument inputs */}
            {argumentInfo.length > 0 && (
              <div className="space-y-1.5">
                <span className="text-[10px] font-semibold text-[var(--color-text-tertiary)] uppercase tracking-[0.06em]">
                  Arguments
                </span>
                {argumentInfo.map((arg) => {
                  const inputType = getInputTypeForHint(arg.type_hint);
                  return (
                    <div key={arg.name} className="flex items-center gap-2">
                      <label className="text-[11px] text-[var(--color-text-secondary)] font-medium min-w-[60px]">
                        {arg.name}
                        <span className="text-[var(--color-text-tertiary)] ml-1 text-[10px]">
                          {arg.type_hint}
                        </span>
                      </label>
                      {inputType === "checkbox" ? (
                        <input
                          type="checkbox"
                          checked={testArgs[arg.name] === "true"}
                          onChange={(e) =>
                            setTestArgs({ ...testArgs, [arg.name]: e.target.checked ? "true" : "false" })
                          }
                          data-testid={`tool-test-arg-${arg.name}`}
                          className="rounded border-[var(--color-border-default)] text-[var(--color-secondary)] focus:ring-[var(--color-secondary)] bg-[var(--color-base)]"
                        />
                      ) : inputType === "textarea" ? (
                        <textarea
                          value={testArgs[arg.name] || ""}
                          onChange={(e) =>
                            setTestArgs({ ...testArgs, [arg.name]: e.target.value })
                          }
                          data-testid={`tool-test-arg-${arg.name}`}
                          className="input-base w-full text-[12px] font-[var(--font-mono)] resize-none"
                          rows={2}
                          placeholder={arg.default_value?.replace(/^['"]|['"]$/g, "") || arg.type_hint}
                        />
                      ) : (
                        <input
                          type={inputType}
                          value={testArgs[arg.name] || ""}
                          onChange={(e) =>
                            setTestArgs({ ...testArgs, [arg.name]: e.target.value })
                          }
                          data-testid={`tool-test-arg-${arg.name}`}
                          className="input-base w-full text-[12px] font-[var(--font-mono)]"
                          placeholder={arg.default_value?.replace(/^['"]|['"]$/g, "") || arg.type_hint}
                          step={arg.type_hint === "int" ? "1" : "any"}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* No-args message */}
            {argumentInfo.length === 0 && (
              <p className="text-[11px] text-[var(--color-text-tertiary)] italic">
                No arguments required
              </p>
            )}

            {/* Action buttons */}
            <div className="flex gap-2">
              <button
                onClick={handleRunTest}
                data-testid="tool-test-run-button"
                className="btn-secondary flex-1 text-[12px]"
                disabled={isTesting}
              >
                Run Test
              </button>
              <button
                onClick={handleResetTest}
                className="btn-ghost text-[11px] px-2 py-1"
              >
                Reset
              </button>
            </div>

            {/* Result panel */}
            {testResult && (
              <div
                className={`rounded-lg p-3 text-[12px] font-[var(--font-mono)] whitespace-pre-wrap break-all max-h-[200px] overflow-auto ${testResult.success
                    ? "bg-[var(--color-success-subtle)] border border-[var(--color-success)]/20 text-[var(--color-text-primary)]"
                    : "bg-[var(--color-danger-subtle)] border border-[var(--color-danger)]/20 text-[var(--color-text-primary)]"
                  }`}
                data-testid="tool-test-result"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className={`text-[10px] font-semibold uppercase tracking-[0.06em] ${testResult.success ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"
                    }`}>
                    {testResult.success ? "Output" : "Error"}
                  </span>
                  <span className="text-[10px] text-[var(--color-text-tertiary)]">
                    {testResult.execution_time_ms.toFixed(1)}ms
                  </span>
                </div>
                {testResult.output}
              </div>
            )}

            {/* Error message (non-result errors) */}
            {testError && !testResult && (
              <div className="rounded-lg p-3 text-[12px] bg-[var(--color-danger-subtle)] border border-[var(--color-danger)]/20 text-[var(--color-danger)]" data-testid="tool-test-error">
                {testError}
              </div>
            )}
          </div>
        )}

        {/* Error state with retry */}
        {testState === "error" && !testResult && !testError && (
          <div className="space-y-2">
            <div className="rounded-lg p-3 text-[12px] bg-[var(--color-danger-subtle)] border border-[var(--color-danger)]/20 text-[var(--color-danger)]">
              Something went wrong. Try again.
            </div>
            <button
              onClick={handleResetTest}
              className="btn-ghost w-full text-[12px]"
            >
              Reset
            </button>
          </div>
        )}
      </div>
    </div>
  );
}