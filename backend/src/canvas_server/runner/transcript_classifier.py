from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolResultClassification:
    agent_name: str
    event_type: str


def classify_tool_result(
    *,
    tool_name: str,
    fallback_agent_name: str,
) -> ToolResultClassification:
    clean_tool_name = tool_name.replace("transfer_to_", "") if tool_name else fallback_agent_name
    is_handoff_tool = tool_name.startswith("transfer_to_") if tool_name else False
    event_type = "response" if is_handoff_tool else "tool_result"
    return ToolResultClassification(agent_name=clean_tool_name, event_type=event_type)
