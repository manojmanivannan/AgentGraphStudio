import { useEffect, useRef } from "react";
import { useCanvasStore } from "@/store/canvasStore";
import { ArrowRight, Wrench, Brain, AlertCircle } from "lucide-react";
import type { ExecutionEvent } from "@/types";

function EventRow({ event }: { event: ExecutionEvent }) {
  const icon = getEventIcon(event);
  const style = getEventStyle(event);
  const label = getEventLabel(event);

  return (
    <div className={`px-3 py-2 text-xs border-b border-gray-50 ${style}`}>
      <div className="flex items-start gap-2">
        <span className="mt-0.5 flex-shrink-0">{icon}</span>
        <div className="flex-1 min-w-0">
          <span className="font-medium text-gray-500">{label}</span>
          <p className="text-gray-700 leading-relaxed break-words">
            {getEventContent(event)}
          </p>
        </div>
      </div>
    </div>
  );
}

function getEventIcon(event: ExecutionEvent) {
  switch (event.type) {
    case "agent_start":
      return <Brain className="w-3 h-3 text-indigo-500" />;
    case "tool_call":
    case "tool_result":
      return <Wrench className="w-3 h-3 text-amber-500" />;
    case "handoff":
      return <ArrowRight className="w-3 h-3 text-purple-500" />;
    case "error":
      return <AlertCircle className="w-3 h-3 text-red-500" />;
    default:
      return <span className="w-3 h-3 rounded-full bg-gray-300 inline-block" />;
  }
}

function getEventStyle(event: ExecutionEvent): string {
  switch (event.type) {
    case "thought":
      return "text-gray-400 italic";
    case "tool_call":
    case "tool_result":
      return "bg-gray-50 font-mono text-gray-600";
    case "handoff":
      return "border-l-2 border-purple-300";
    case "final_answer":
      return "font-semibold text-indigo-700 bg-indigo-50";
    case "error":
      return "text-red-600 bg-red-50";
    case "agent_start":
      return "font-medium text-indigo-600 bg-indigo-50/50";
    default:
      return "";
  }
}

function getEventLabel(event: ExecutionEvent): string {
  switch (event.type) {
    case "run_start":
      return "Started";
    case "agent_start":
      return `Agent: ${event.agent}`;
    case "thought":
      return `Thought — ${event.agent}`;
    case "tool_call":
      return `Tool Call — ${event.tool}`;
    case "tool_result":
      return `Tool Result — ${event.tool}`;
    case "handoff":
      return `Handoff`;
    case "final_answer":
      return "Final Answer";
    case "run_complete":
      return "Completed";
    case "error":
      return "Error";
    default:
      return "";
  }
}

function getEventContent(event: ExecutionEvent): string {
  switch (event.type) {
    case "thought":
      return event.content;
    case "tool_call":
      return JSON.stringify(event.input, null, 1);
    case "tool_result":
      return typeof event.output === "string" ? event.output : JSON.stringify(event.output);
    case "handoff":
      return `${event.from} → ${event.to}`;
    case "final_answer":
      return event.content;
    case "error":
      return event.message;
    case "run_complete":
      return event.result;
    default:
      return "";
  }
}

export function ExecutionLog() {
  const executionEvents = useCanvasStore((s) => s.executionEvents);
  const executionStatus = useCanvasStore((s) => s.executionStatus);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [executionEvents]);

  if (executionEvents.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        {executionStatus === "running" ? (
          <span className="flex items-center gap-2">
            <span className="w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
            Running...
          </span>
        ) : (
          <>Run your workflow to see execution events</>
        )}
      </div>
    );
  }

  return (
    <div ref={scrollRef} className="h-full overflow-y-auto">
      <div className="divide-y divide-gray-50">
        {executionEvents.map((event, i) => (
          <EventRow key={i} event={event} />
        ))}
        {executionStatus === "running" && (
          <div className="flex items-center justify-center py-4">
            <span className="w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
          </div>
        )}
      </div>
    </div>
  );
}
