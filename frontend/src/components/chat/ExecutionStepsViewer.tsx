/**
 * @fileoverview Collapsible viewer for rendering agent reasoning steps (thoughts,
 * tool executions, routing events) generated during the ReAct loop.
 */

import { ChevronDown, ChevronRight } from "lucide-react";
import type { Message } from "@/types";

interface ActiveInterrupt {
  message_id: string;
  tool?: string;
  args?: Record<string, any>;
}

interface ExecutionStepsViewerProps {
  steps: Message[];
  isStreaming: boolean;
  isExpanded: boolean;
  collapsedSteps: Set<string>;
  toggleStepExpand: (stepId: string) => void;
  getMessageNestingLevel: (msg: Message) => number;
  activeInterrupt?: ActiveInterrupt | null;
  handleSendHumanResponse: (val: string) => void;
  handleSendToolApproval: (val: boolean) => void;
  inlineInputRef: React.RefObject<HTMLInputElement | null>;
  renderMessageContent: (content: string, isSmall?: boolean) => React.ReactNode;
}

export function ExecutionStepsViewer({
  steps,
  isStreaming,
  isExpanded,
  collapsedSteps,
  toggleStepExpand,
  getMessageNestingLevel,
  activeInterrupt,
  handleSendHumanResponse,
  handleSendToolApproval,
  inlineInputRef,
  renderMessageContent,
}: ExecutionStepsViewerProps) {
  const hasSteps = steps.length > 0;
  if (!hasSteps || (!isStreaming && !isExpanded)) return null;

  return (
    <div className="ml-3 pl-3 border-l-2 border-[var(--color-border-subtle)] space-y-2.5">
      {steps.map((stepMsg) => {
        const isThought = stepMsg.event_type === "thought";
        const isHandoff = stepMsg.event_type === "handoff";
        const isToolResult = stepMsg.event_type === "tool_result";
        const isError = stepMsg.event_type === "error";
        const isSubAnswer = stepMsg.event_type === "final_answer";
        const isWarning = stepMsg.event_type === "warning";
        const isResponse = stepMsg.event_type === "response";

        const level = getMessageNestingLevel(stepMsg);
        const isStepCollapsed = collapsedSteps.has(stepMsg.id);

        return (
          <div
            key={stepMsg.id}
            className="flex flex-col items-start w-full"
            style={{
              animation: "staggerFadeIn 0.3s ease-out",
              paddingLeft: `${level * 24}px`,
              transition: "padding-left 0.2s ease-out",
            }}
          >
            <button
              onClick={() => toggleStepExpand(stepMsg.id)}
              className="flex items-center gap-1.5 text-[10px] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] transition-colors cursor-pointer px-1 font-semibold tracking-wide mb-0.5"
            >
              {isStepCollapsed ? (
                <ChevronRight className="w-3 h-3" />
              ) : (
                <ChevronDown className="w-3 h-3" />
              )}
              <span>
                {stepMsg.agent_name || (isError || isWarning || isHandoff ? "System" : "Agent")}
                {stepMsg.event_type && stepMsg.event_type !== "final_answer" && ` · ${stepMsg.event_type}`}
              </span>
            </button>

            {!isStepCollapsed && (
              <div
                className={`max-w-[85%] w-full rounded-xl px-3 py-2 text-[12px] leading-relaxed shadow-sm ${
                  isHandoff
                    ? "bg-[var(--color-info-subtle)] text-[var(--color-info)] border border-[var(--color-info)]/20 rounded-bl-sm"
                    : isError
                    ? "bg-[var(--color-danger-subtle)] text-[var(--color-danger)] border border-[var(--color-danger)]/20 rounded-bl-sm"
                    : isWarning || stepMsg.event_type === "tool_approval_request"
                    ? "bg-[var(--color-warning-subtle)] text-[var(--color-warning)] border border-[var(--color-warning)]/20 rounded-bl-sm"
                    : isThought
                    ? "bg-[var(--color-agent-subtle)] text-[var(--color-agent)] border border-[var(--color-agent)]/20 rounded-bl-sm font-mono whitespace-pre-wrap text-[11px]"
                    : stepMsg.event_type === "human_input_request"
                    ? "bg-[var(--color-agent-subtle)] text-[var(--color-agent)] border border-[var(--color-agent)]/20 rounded-bl-sm"
                    : isToolResult
                    ? "bg-[var(--color-success-subtle)] text-[var(--color-success)] border border-[var(--color-success)]/20 rounded-bl-sm font-mono"
                    : isResponse
                    ? "bg-[var(--color-agent-subtle)] text-[var(--color-agent)] border border-[var(--color-agent)]/20 rounded-bl-sm"
                    : isSubAnswer
                    ? "bg-[var(--color-elevated)] text-[var(--color-text-secondary)] border border-[var(--color-border-subtle)] rounded-bl-sm"
                    : "bg-[var(--color-elevated)] text-[var(--color-text-primary)] border border-[var(--color-border-subtle)] rounded-bl-sm"
                }`}
              >
                {stepMsg.event_type === "human_input_request" && stepMsg.id === activeInterrupt?.message_id ? (
                  <div className="space-y-3 w-full">
                    <div className="text-[var(--color-text-primary)] font-medium">
                      {stepMsg.content}
                    </div>
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        const form = e.currentTarget;
                        const data = new FormData(form);
                        const val = (data.get("response") as string || "").trim();
                        if (!val) return;
                        handleSendHumanResponse(val);
                      }}
                      className="flex gap-2 w-full mt-1.5"
                    >
                      <input
                        ref={inlineInputRef}
                        name="response"
                        type="text"
                        required
                        placeholder="Type your response..."
                        className="input-base flex-1 py-1.5 px-3 rounded-lg text-[12px] bg-[var(--color-base)] text-[var(--color-text-primary)] border border-[var(--color-border-default)] focus:border-[var(--color-accent)]"
                      />
                      <button
                        type="submit"
                        className="px-3.5 py-1.5 bg-[var(--color-accent)] hover:bg-[var(--color-accent-bright)] text-white text-[11px] font-semibold rounded-lg shadow transition-colors"
                      >
                        Submit
                      </button>
                    </form>
                  </div>
                ) : stepMsg.event_type === "tool_approval_request" && stepMsg.id === activeInterrupt?.message_id ? (
                  <div className="space-y-2.5 w-full">
                    <div className="text-[var(--color-text-primary)] font-medium flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-[var(--color-warning)] animate-ping" />
                      <span>Tool Approval Required</span>
                    </div>
                    <div className="bg-[var(--color-base)] border border-[var(--color-border-subtle)] rounded-lg p-2.5 font-mono text-[11px] text-[var(--color-text-secondary)] space-y-1 max-w-full overflow-x-auto">
                      <div><strong>Tool:</strong> {activeInterrupt.tool}</div>
                      {activeInterrupt.args && Object.keys(activeInterrupt.args).length > 0 && (
                        <div>
                          <strong>Arguments:</strong>
                          <pre className="mt-1 p-1.5 bg-[var(--color-elevated)] rounded border border-[var(--color-border-subtle)]/50 text-[10px] overflow-x-auto whitespace-pre-wrap">
                            {JSON.stringify(activeInterrupt.args, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                    <div className="flex gap-2 mt-1">
                      <button
                        onClick={() => handleSendToolApproval(true)}
                        className="px-3.5 py-1.5 bg-[var(--color-success)] hover:bg-[var(--color-success)]/90 text-white text-[11px] font-semibold rounded-lg shadow flex items-center gap-1 transition-colors"
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => handleSendToolApproval(false)}
                        className="px-3.5 py-1.5 bg-[var(--color-danger)] hover:bg-[var(--color-danger)]/90 text-white text-[11px] font-semibold rounded-lg shadow flex items-center gap-1 transition-colors"
                      >
                        Deny
                      </button>
                    </div>
                  </div>
                ) : (
                  renderMessageContent(stepMsg.content, true)
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
