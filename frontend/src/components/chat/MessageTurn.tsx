/**
 * @fileoverview Renders a single conversational turn, consisting of a user message
 * followed by the agent's execution steps, potential human-in-the-loop (HITL) requests,
 * and the final answer.
 */

import { ChevronDown, ChevronRight } from "lucide-react";
import type { Message } from "@/types";
import { ExecutionStepsViewer } from "./ExecutionStepsViewer";

export interface TurnGroup {
  id: string;
  userMessage: Message;
  steps: Message[];
  humanInterrupt?: Message;
  finalAnswer?: Message;
  isStreaming: boolean;
}

interface MessageTurnProps {
  turn: TurnGroup;
  running: boolean;
  expandedTurns: Set<string>;
  toggleExpand: (turnId: string) => void;
  collapsedSteps: Set<string>;
  toggleStepExpand: (stepId: string) => void;
  getMessageNestingLevel: (msg: Message) => number;
  activeInterrupt?: any;
  handleSendHumanResponse: (val: string) => void;
  handleSendToolApproval: (val: boolean) => void;
  inlineInputRef: React.RefObject<HTMLInputElement | null>;
  renderMessageContent: (content: string, isSmall?: boolean) => React.ReactNode;
}

export function MessageTurn({
  turn,
  running,
  expandedTurns,
  toggleExpand,
  collapsedSteps,
  toggleStepExpand,
  getMessageNestingLevel,
  activeInterrupt,
  handleSendHumanResponse,
  handleSendToolApproval,
  inlineInputRef,
  renderMessageContent,
}: MessageTurnProps) {
  const isStreaming = turn.isStreaming && running;
  const isExpanded = expandedTurns.has(turn.id);
  const hasSteps = turn.steps.length > 0;

  return (
    <div className="space-y-3">
      {/* User Message */}
      <div className="flex flex-col items-end" style={{ animation: "staggerFadeIn 0.3s ease-out" }}>
        <div className="max-w-[85%] rounded-2xl px-4 py-2.5 text-[13px] leading-relaxed bg-[var(--color-accent)] text-[var(--color-text-inverse)] rounded-br-sm shadow-md font-medium">
          {turn.userMessage.content}
        </div>
      </div>

      {/* Steps toggle */}
      {!isStreaming && hasSteps && (
        <button
          onClick={() => toggleExpand(turn.id)}
          className="flex items-center gap-1.5 text-[11px] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] transition-colors cursor-pointer px-1 font-semibold"
        >
          {isExpanded ? (
            <>
              <ChevronDown className="w-3.5 h-3.5" />
              <span>Hide execution steps</span>
            </>
          ) : (
            <>
              <ChevronRight className="w-3.5 h-3.5" />
              <span>
                Show {turn.steps.length} execution step{turn.steps.length !== 1 && "s"}
              </span>
            </>
          )}
        </button>
      )}

      {/* Steps Container */}
      <ExecutionStepsViewer
        steps={turn.steps}
        isStreaming={isStreaming}
        isExpanded={isExpanded}
        collapsedSteps={collapsedSteps}
        toggleStepExpand={toggleStepExpand}
        getMessageNestingLevel={getMessageNestingLevel}
        activeInterrupt={activeInterrupt}
        handleSendHumanResponse={handleSendHumanResponse}
        handleSendToolApproval={handleSendToolApproval}
        inlineInputRef={inlineInputRef}
        renderMessageContent={renderMessageContent}
      />

      {/* Human Interrupt Request (visible outside only when collapsed) */}
      {!isStreaming && !isExpanded && turn.humanInterrupt && (
        <div
          className="flex flex-col items-start w-full animate-fade-in"
          style={{ animation: "staggerFadeIn 0.3s ease-out" }}
        >
          {turn.humanInterrupt.agent_name && (
            <span className="text-[10px] text-[var(--color-text-tertiary)] mb-0.5 px-1 font-semibold tracking-wide">
              {turn.humanInterrupt.agent_name} · {turn.humanInterrupt.event_type === "tool_approval_request" ? "tool_approval_request" : "human_input_request"}
            </span>
          )}
          <div
            className={`max-w-[85%] w-full rounded-xl px-3 py-2.5 text-[12px] leading-relaxed shadow-sm ${
              turn.humanInterrupt.event_type === "tool_approval_request"
                ? "bg-[var(--color-warning-subtle)] text-[var(--color-warning)] border border-[var(--color-warning)]/20 rounded-bl-sm"
                : "bg-[var(--color-agent-subtle)] text-[var(--color-agent)] border border-[var(--color-agent)]/20 rounded-bl-sm"
            }`}
          >
            {turn.humanInterrupt.event_type === "human_input_request" && turn.humanInterrupt.id === activeInterrupt?.message_id ? (
              <div className="space-y-3 w-full">
                <div className="text-[var(--color-text-primary)] font-medium">
                  {turn.humanInterrupt.content}
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
            ) : turn.humanInterrupt.event_type === "tool_approval_request" && turn.humanInterrupt.id === activeInterrupt?.message_id ? (
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
              renderMessageContent(turn.humanInterrupt.content, true)
            )}
          </div>
        </div>
      )}

      {/* Final Answer */}
      {turn.finalAnswer && (
        <div
          className="flex flex-col items-start"
          style={{ animation: "staggerFadeIn 0.3s ease-out" }}
        >
          {turn.finalAnswer.agent_name && (
            <span className="text-[10px] text-[var(--color-text-tertiary)] mb-0.5 px-1 font-semibold tracking-wide">
              {turn.finalAnswer.agent_name}
            </span>
          )}
          <div className="max-w-[85%] rounded-2xl px-4 py-3 text-[14px] leading-relaxed bg-[var(--color-elevated)] text-[var(--color-text-primary)] border border-[var(--color-border-subtle)] shadow-sm rounded-bl-sm">
            {renderMessageContent(turn.finalAnswer.content, false)}
          </div>
        </div>
      )}
    </div>
  );
}
