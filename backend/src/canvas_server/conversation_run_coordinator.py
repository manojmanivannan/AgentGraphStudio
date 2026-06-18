import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from canvas_server.runner import CanvasRunner

EventSender = Callable[[dict[str, Any]], Awaitable[None]]


class ConversationRunCoordinator:
    def __init__(
        self,
        *,
        session,
        conversation_repo,
        canvas_repo,
        runner_factory: Callable[..., Awaitable[Any]] | None = None,
    ):
        self.session = session
        self.conversation_repo = conversation_repo
        self.canvas_repo = canvas_repo
        self.runner_factory = runner_factory or self._build_runner

    async def run(
        self,
        *,
        conversation_id: uuid.UUID,
        user_prompt: str,
        send_event: EventSender,
        target_agent_id: uuid.UUID | None = None,
    ) -> None:
        conversation = await self.conversation_repo.get_or_404(conversation_id)
        canvas = await self.canvas_repo.get_or_404(conversation.canvas_id)
        runner = await self.runner_factory(
            canvas=canvas,
            conversation_repo=self.conversation_repo,
            conversation_id=conversation_id,
        )

        try:
            await self._rename_initial_conversation(
                conversation=conversation,
                conversation_id=conversation_id,
                user_prompt=user_prompt,
                runner=runner,
                send_event=send_event,
            )
            await runner.run(
                user_prompt,
                send_event,
                target_agent_id=target_agent_id,
            )
        except Exception as exc:
            primary_agent = self._resolve_primary_agent(
                canvas=canvas,
                target_agent_id=target_agent_id,
            )
            await self._persist_error(
                runner=runner,
                error=exc,
                agent_name=primary_agent["agent"],
                node_id=primary_agent["node_id"],
            )
            event = {
                "type": "final_answer",
                "content": str(exc),
            }
            if primary_agent["agent"]:
                event["agent"] = primary_agent["agent"]
            if primary_agent["node_id"]:
                event["node_id"] = primary_agent["node_id"]
            await send_event(event)
        finally:
            await self.session.commit()

    async def _build_runner(self, *, canvas, conversation_repo, conversation_id):
        return CanvasRunner(
            canvas,
            conversation_repo=conversation_repo,
            conversation_id=conversation_id,
        )

    async def _rename_initial_conversation(
        self,
        *,
        conversation,
        conversation_id: uuid.UUID,
        user_prompt: str,
        runner,
        send_event: EventSender,
    ) -> None:
        if conversation.messages or conversation.name != "New Conversation":
            return

        new_name = await runner.generate_conversation_title(user_prompt)
        if not new_name:
            new_name = self._fallback_title(user_prompt)

        if not new_name:
            return

        await self.conversation_repo.update_name(conversation_id, new_name)
        await self.session.commit()
        await send_event(
            {
                "type": "conversation_renamed",
                "conversation_id": str(conversation_id),
                "name": new_name,
            }
        )

    async def _persist_error(
        self,
        *,
        runner,
        error: Exception,
        agent_name: str | None = None,
        node_id: str | None = None,
    ) -> None:
        try:
            await runner._conversation.persist_message(
                role="assistant",
                content=str(error),
                agent_name=agent_name,
                node_id=node_id,
                event_type="final_answer",
            )
            await self.session.commit()
        except Exception:
            pass

    def _resolve_primary_agent(
        self,
        *,
        canvas,
        target_agent_id: uuid.UUID | None,
    ) -> dict[str, str | None]:
        agent_nodes = getattr(canvas, "agent_nodes", None) or []
        if not agent_nodes:
            return {"agent": None, "node_id": None}

        selected = None
        if target_agent_id is not None:
            selected = next((n for n in agent_nodes if getattr(n, "id", None) == target_agent_id), None)
        if selected is None:
            selected = agent_nodes[0]

        agent_name = getattr(selected, "name", None)
        node_id = getattr(selected, "id", None)
        return {
            "agent": agent_name,
            "node_id": str(node_id) if node_id else None,
        }

    def _fallback_title(self, user_prompt: str) -> str | None:
        try:
            first_line = (user_prompt or "").strip().splitlines()[0]
            tokens = first_line.split()
            fallback = " ".join(tokens[:6]) if tokens else "Chat"
            return fallback[:100].strip(" .?!") or None
        except Exception:
            return None
