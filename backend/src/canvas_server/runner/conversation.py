"""ConversationService — loads, persists, and formats conversation history."""

from __future__ import annotations

import logging
import uuid

import dspy

logger = logging.getLogger("canvas_server.runner.conversation")


class ConversationService:
    """Handles all interaction with conversation and message persistence.

    State owned by this service: none (pure delegate to ``conversation_repo``).
    The repo reference is injected and may be ``None`` when running outside a
    request context (e.g. tests).
    """

    def __init__(self, conversation_repo=None, conversation_id=None):
        self.conversation_repo = conversation_repo
        self.conversation_id = conversation_id
        import asyncio
        self._lock = asyncio.Lock()

    async def load_messages(self) -> list:
        """Return all messages for the current conversation, or ``[]``."""
        if not self.conversation_repo or not self.conversation_id:
            return []
        try:
            conv = await self.conversation_repo.get(self.conversation_id)
            if conv:
                return list(conv.messages)
        except Exception:
            pass
        return []

    async def persist_message(
        self,
        role: str,
        content: str,
        agent_name: str | None = None,
        node_id: uuid.UUID | None = None,
        event_type: str | None = None,
    ):
        has_repo = self.conversation_repo is not None
        logger.info(
            "persist_message called: role=%s, event_type=%s, agent_name=%s, repo=%s, conv_id=%s",
            role,
            event_type,
            agent_name,
            has_repo,
            self.conversation_id,
        )
        if not self.conversation_repo or not self.conversation_id:
            return
        async with self._lock:
            try:
                await self.conversation_repo.add_message(
                    conversation_id=self.conversation_id,
                    role=role,
                    content=content,
                    agent_name=agent_name,
                    node_id=node_id,
                    event_type=event_type,
                )
            except Exception as e:
                logger.error("Failed to persist message: %s", e, exc_info=True)

    def format_history(
        self,
        messages: list,
        history_enabled_node_ids: set[uuid.UUID] | None = None,
    ) -> str:
        """Format *messages* as a plain-text conversation summary.

        * System prompts (``role == "system"``) are skipped — they're already in
          the DSPy signature instructions.
        * Assistant messages from agents NOT in *history_enabled_node_ids* are
          skipped — intermediate sub-agent responses are internal details.
        """
        if not messages:
            return ""
        lines = ["## Conversation History"]
        for msg in messages:
            if msg.role == "system":
                continue
            if (
                msg.role == "assistant"
                and history_enabled_node_ids is not None
                and msg.node_id not in history_enabled_node_ids
            ):
                continue
            event_type = (
                getattr(msg, "event_type", None)
                if not isinstance(msg, dict)
                else msg.get("event_type")
            )
            if msg.role == "assistant" and event_type not in (None, "final_answer"):
                continue
            if msg.agent_name and msg.role == "assistant":
                label = f"Assistant [{msg.agent_name}]"
            else:
                label = msg.role.capitalize()
            lines.append(f"{label}: {msg.content}")
            lines.append("---")
        return "\n".join(lines)

    def build_dspy_history(
        self,
        messages: list,
        history_enabled_node_ids: set[uuid.UUID],
    ) -> dspy.History | None:
        """Build a ``dspy.History`` from stored conversation messages.

        Only user messages and assistant messages from history-enabled agents
        are included. System prompts and intermediate sub-agent responses are
        excluded.
        """
        if not messages:
            return None
        dspy_messages = []
        for msg in messages:
            if msg.role == "system":
                continue
            elif msg.role == "user":
                dspy_messages.append({"user_request": msg.content})
            elif msg.role == "assistant" and msg.node_id in history_enabled_node_ids:
                event_type = (
                    getattr(msg, "event_type", None)
                    if not isinstance(msg, dict)
                    else msg.get("event_type")
                )
                if event_type in (None, "final_answer"):
                    dspy_messages.append({"process_result": msg.content})
        if not dspy_messages:
            return None
        return dspy.History(messages=dspy_messages)

    def build_conversation_history_context(
        self,
        messages: list,
        history_enabled_node_ids: set[uuid.UUID],
    ) -> tuple[str, dspy.History | None]:
        """Convenience: return ``(history_text, dspy_history)`` from *messages*.

        This is the common call site in ``run()`` — it produces both the
        plain-text summary (for the worker prompt) and the structured DSPy
        history object in one go.
        """
        history_text = self.format_history(messages, history_enabled_node_ids)

        dspy_history = self.build_dspy_history(messages, history_enabled_node_ids)

        return history_text, dspy_history
