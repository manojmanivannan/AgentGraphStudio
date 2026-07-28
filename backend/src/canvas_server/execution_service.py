from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from canvas_server.background_run_worker import TERMINAL_RUN_STATUSES


class SessionProtocol(Protocol):
    async def commit(self) -> None: ...


class SessionFactoryProtocol(Protocol):
    def __call__(self) -> Any: ...


class ConversationRepoProtocol(Protocol):
    async def get_or_404(self, conversation_id: uuid.UUID) -> Any: ...
    async def get_plot(self, plot_id: uuid.UUID) -> Any | None: ...


class DurableRunRepoProtocol(Protocol):
    async def create(
        self,
        *,
        conversation_id: uuid.UUID,
        prompt: str,
        target_agent_id: uuid.UUID | None = None,
    ) -> Any: ...

    async def get(self, run_id: uuid.UUID) -> Any | None: ...
    async def get_or_404(self, run_id: uuid.UUID) -> Any: ...
    async def list_events(self, run_id: uuid.UUID, *, after_sequence: int = 0) -> list[Any]: ...
    async def get_latest_active_for_conversation(self, conversation_id: uuid.UUID) -> Any | None: ...
    async def append_event(self, run_id: uuid.UUID, *, event_type: str, payload: dict) -> Any: ...
    async def mark_aborting(self, run_id: uuid.UUID) -> Any: ...


class WorkerProtocol(Protocol):
    async def ensure_started(self) -> None: ...
    async def subscribe(self, run_id: uuid.UUID) -> Any: ...
    async def unsubscribe(self, run_id: uuid.UUID, queue: Any) -> None: ...
    async def submit_interrupt_response(self, request_id: str, response: dict) -> bool: ...
    def kick(self) -> None: ...


@dataclass(frozen=True)
class PlotPayload:
    content: bytes
    media_type: str


@dataclass(frozen=True)
class RunStartRequest:
    conversation_id: uuid.UUID
    prompt: str
    requested_run_id: uuid.UUID | None = None
    target_agent_id: uuid.UUID | None = None


@dataclass(frozen=True)
class RunStartResult:
    run_id: uuid.UUID
    is_new_run: bool


class ExecutionService:
    def __init__(
        self,
        *,
        session_factory: SessionFactoryProtocol,
        conversation_repo_factory: Callable[[Any], ConversationRepoProtocol] | None = None,
        durable_run_repo_factory: Callable[[Any], DurableRunRepoProtocol] | None = None,
        worker_provider: Callable[[], WorkerProtocol] | None = None,
        execution_mode: str = "worker",
    ) -> None:
        self._session_factory = session_factory
        self._conversation_repo_factory = conversation_repo_factory
        self._durable_run_repo_factory = durable_run_repo_factory
        self._worker_provider = worker_provider
        self._execution_mode = execution_mode

    async def get_plot_payload(self, plot_id: uuid.UUID) -> PlotPayload:
        if self._conversation_repo_factory is None:
            raise RuntimeError("conversation_repo_factory is required")

        async with self._session_factory() as session:
            conv_repo = self._conversation_repo_factory(session)
            plot = await conv_repo.get_plot(plot_id)
            if plot is None:
                raise LookupError("Plot not found")
            return PlotPayload(content=plot.content, media_type=f"image/{plot.format}")

    async def get_active_run(self, conversation_id: uuid.UUID) -> dict[str, Any] | None:
        if self._conversation_repo_factory is None or self._durable_run_repo_factory is None:
            raise RuntimeError("conversation_repo_factory and durable_run_repo_factory are required")

        async with self._session_factory() as session:
            conv_repo = self._conversation_repo_factory(session)
            await conv_repo.get_or_404(conversation_id)

            run_repo = self._durable_run_repo_factory(session)
            run = await run_repo.get_latest_active_for_conversation(conversation_id)
            if run is None:
                return None

            return {
                "run_id": str(run.id),
                "conversation_id": str(run.conversation_id),
                "status": run.status,
                "replay_cursor": run.replay_cursor,
            }

    async def get_run_events_after(self, *, run_id: uuid.UUID, after_sequence: int) -> list[dict]:
        if self._durable_run_repo_factory is None:
            raise RuntimeError("durable_run_repo_factory is required")

        async with self._session_factory() as session:
            run_repo = self._durable_run_repo_factory(session)
            events = await run_repo.list_events(run_id, after_sequence=after_sequence)

        replay: list[dict] = []
        for event in events:
            payload = dict(event.payload or {})
            payload.setdefault("type", event.event_type)
            payload["sequence"] = event.sequence
            payload["run_id"] = str(run_id)
            replay.append(payload)
        return replay

    async def get_run_status(self, run_id: uuid.UUID) -> str | None:
        if self._durable_run_repo_factory is None:
            raise RuntimeError("durable_run_repo_factory is required")

        async with self._session_factory() as session:
            run_repo = self._durable_run_repo_factory(session)
            run = await run_repo.get(run_id)
        return run.status if run else None

    async def prepare_run(self, request: RunStartRequest) -> RunStartResult:
        if self._conversation_repo_factory is None or self._durable_run_repo_factory is None:
            raise RuntimeError("conversation_repo_factory and durable_run_repo_factory are required")

        async with self._session_factory() as session:
            conv_repo = self._conversation_repo_factory(session)
            await conv_repo.get_or_404(request.conversation_id)

            run_repo = self._durable_run_repo_factory(session)

            if request.requested_run_id is not None:
                existing_run = await run_repo.get_or_404(request.requested_run_id)
                if existing_run.conversation_id != request.conversation_id:
                    raise ValueError("Run does not belong to conversation")
                return RunStartResult(run_id=existing_run.id, is_new_run=False)

            if not request.prompt:
                raise ValueError("prompt is required when run_id is not provided")

            run = await run_repo.create(
                conversation_id=request.conversation_id,
                prompt=request.prompt,
                target_agent_id=request.target_agent_id,
            )
            return RunStartResult(run_id=run.id, is_new_run=True)

    async def submit_interrupt_response(self, *, run_id: uuid.UUID, body: dict) -> dict[str, Any]:
        request_id = body.get("request_id")
        if not request_id:
            raise ValueError("request_id is required")

        if self._durable_run_repo_factory is None:
            raise RuntimeError("durable_run_repo_factory is required")

        async with self._session_factory() as session:
            run_repo = self._durable_run_repo_factory(session)
            await run_repo.get_or_404(run_id)
            await run_repo.append_event(
                run_id,
                event_type="interrupt_response",
                payload=body,
            )
            await session.commit()

        try:
            worker = self.get_worker()
            if worker is not None:
                await worker.submit_interrupt_response(request_id, body)
        except Exception:
            # In API-only mode, there may be no in-process worker to notify.
            pass

        return {"ok": True, "request_id": request_id}

    async def abort_run(self, run_id: uuid.UUID) -> dict[str, Any]:
        if self._durable_run_repo_factory is None:
            raise RuntimeError("durable_run_repo_factory is required")

        async with self._session_factory() as session:
            run_repo = self._durable_run_repo_factory(session)
            run = await run_repo.get_or_404(run_id)

            if run.status in TERMINAL_RUN_STATUSES:
                return {
                    "run_id": str(run.id),
                    "status": run.status,
                }

            updated = await run_repo.mark_aborting(run_id)
            await session.commit()

            return {
                "run_id": str(updated.id),
                "status": updated.status,
            }

    def should_use_local_worker(self) -> bool:
        return self._execution_mode != "api"

    def get_worker(self) -> WorkerProtocol | None:
        if self._worker_provider is None:
            return None
        return self._worker_provider()