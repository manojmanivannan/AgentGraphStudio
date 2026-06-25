from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from canvas_server.conversation_run_coordinator import ConversationRunCoordinator
from canvas_server.database import get_session_factory
from canvas_server.exceptions import RunAbortedError
from canvas_server.repos.canvas_repo import CanvasRepo
from canvas_server.repos.conversation_repo import ConversationRepo
from canvas_server.repos.durable_run_repo import DurableRunRepo

logger = logging.getLogger("canvas_server.background_worker")

TERMINAL_RUN_STATUSES = {"completed", "failed", "aborted"}


class RunEventBroker:
    def __init__(self) -> None:
        self._subscribers: dict[uuid.UUID, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, run_id: uuid.UUID) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        async with self._lock:
            self._subscribers[run_id].add(queue)
        return queue

    async def unsubscribe(self, run_id: uuid.UUID, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            subscribers = self._subscribers.get(run_id)
            if not subscribers:
                return
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(run_id, None)

    async def publish(self, run_id: uuid.UUID, event: dict[str, Any]) -> None:
        async with self._lock:
            subscribers = list(self._subscribers.get(run_id, set()))

        for queue in subscribers:
            queue.put_nowait(event)


class InterruptStore:
    """Holds in-memory asyncio Futures for pending HITL / tool-approval interrupts.

    Each pending interrupt is keyed by its request_id.  The executing worker
    creates a Future via ``wait_for_response``, which blocks until the API
    route resolves it via ``resolve``.
    """

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def wait_for_response(self, request_id: str) -> dict[str, Any]:
        """Register *request_id* and await its resolution."""
        loop = asyncio.get_event_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        async with self._lock:
            self._pending[request_id] = future
        try:
            return await future
        finally:
            async with self._lock:
                self._pending.pop(request_id, None)

    async def resolve(self, request_id: str, response: dict[str, Any]) -> bool:
        """Deliver *response* to the waiting coroutine.  Returns True if resolved."""
        async with self._lock:
            future = self._pending.get(request_id)
        if future is not None and not future.done():
            future.set_result(response)
            return True
        return False


class BackgroundRunWorker:
    def __init__(
        self,
        *,
        session_factory: Callable[..., async_sessionmaker[AsyncSession]],
        worker_id: str | None = None,
        lease_seconds: int = 30,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        self._session_factory = session_factory
        self.worker_id = worker_id or f"worker-{uuid.uuid4()}"
        self.lease_seconds = lease_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self._wake_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._worker_task: asyncio.Task | None = None
        self._broker = RunEventBroker()
        self._interrupt_store = InterruptStore()

    async def ensure_started(self) -> None:
        if self._worker_task and not self._worker_task.done():
            return

        self._stop_event.clear()
        self._wake_event.clear()
        self._worker_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if not self._worker_task:
            return

        self._stop_event.set()
        self._wake_event.set()
        try:
            await self._worker_task
        finally:
            self._worker_task = None

    def kick(self) -> None:
        self._wake_event.set()

    async def subscribe(self, run_id: uuid.UUID) -> asyncio.Queue[dict[str, Any]]:
        return await self._broker.subscribe(run_id)

    async def unsubscribe(self, run_id: uuid.UUID, queue: asyncio.Queue[dict[str, Any]]) -> None:
        await self._broker.unsubscribe(run_id, queue)

    async def process_once(self) -> bool:
        now = datetime.now(UTC)
        lease_expires_at = now + timedelta(seconds=self.lease_seconds)

        async with self._session_factory() as session:
            run_repo = DurableRunRepo(session)
            run = await run_repo.claim_next_runnable(
                lease_owner=self.worker_id,
                lease_expires_at=lease_expires_at,
                now=now,
            )
            if run is None:
                await session.commit()
                return False

            run_id = run.id
            prompt = run.prompt
            target_agent_id = run.target_agent_id
            conversation_id = run.conversation_id
            await session.commit()

        await self._execute_run(
            run_id=run_id,
            conversation_id=conversation_id,
            prompt=prompt,
            target_agent_id=target_agent_id,
        )
        return True

    async def _run_loop(self) -> None:
        logger.info("Background run worker started: %s", self.worker_id)
        try:
            while not self._stop_event.is_set():
                claimed = await self.process_once()
                if claimed:
                    continue

                try:
                    await asyncio.wait_for(
                        self._wake_event.wait(), timeout=self.poll_interval_seconds
                    )
                except TimeoutError:
                    pass
                finally:
                    self._wake_event.clear()
        finally:
            logger.info("Background run worker stopped: %s", self.worker_id)

    async def _execute_run(
        self,
        *,
        run_id: uuid.UUID,
        conversation_id: uuid.UUID,
        prompt: str,
        target_agent_id: uuid.UUID | None,
    ) -> None:
        async with self._session_factory() as session:
            conv_repo = ConversationRepo(session)
            canvas_repo = CanvasRepo(session)
            run_repo = DurableRunRepo(session)
            coordinator = ConversationRunCoordinator(
                session=session,
                conversation_repo=conv_repo,
                canvas_repo=canvas_repo,
            )

            async def send_event(event: dict[str, Any]) -> None:
                current_run = await run_repo.get_or_404(run_id)
                if current_run.status == "aborting":
                    raise RunAbortedError("Run aborted by user")

                event_type = str(event.get("type", "event"))
                durable_event = await run_repo.append_event(
                    run_id,
                    event_type=event_type,
                    payload=event,
                )
                await session.commit()

                payload = dict(event)
                payload["sequence"] = durable_event.sequence
                payload["run_id"] = str(run_id)
                await self._broker.publish(run_id, payload)

            async def get_client_response(request_id: str, response_type: str) -> dict[str, Any]:
                return await self._interrupt_store.wait_for_response(request_id)

            try:
                await coordinator.run(
                    conversation_id=conversation_id,
                    user_prompt=prompt,
                    send_event=send_event,
                    target_agent_id=target_agent_id,
                    get_client_response=get_client_response,
                )
                latest_run = await run_repo.get_or_404(run_id)
                if latest_run.status == "aborting":
                    aborted_payload = {
                        "type": "run_aborted",
                        "message": "Run aborted by user",
                        "run_id": str(run_id),
                    }
                    durable_event = await run_repo.append_event(
                        run_id,
                        event_type="run_aborted",
                        payload=aborted_payload,
                    )
                    await run_repo.mark_aborted(run_id, reason="Run aborted by user")
                    await session.commit()
                    aborted_payload["sequence"] = durable_event.sequence
                    await self._broker.publish(run_id, aborted_payload)
                    return

                await run_repo.mark_completed(run_id)
                await session.commit()
            except RunAbortedError as exc:
                aborted_payload = {
                    "type": "run_aborted",
                    "message": str(exc),
                    "run_id": str(run_id),
                }
                durable_event = await run_repo.append_event(
                    run_id,
                    event_type="run_aborted",
                    payload=aborted_payload,
                )
                await run_repo.mark_aborted(run_id, reason=str(exc))
                await session.commit()
                aborted_payload["sequence"] = durable_event.sequence
                await self._broker.publish(run_id, aborted_payload)
            except Exception as exc:
                error_payload = {
                    "type": "error",
                    "message": str(exc),
                    "run_id": str(run_id),
                }
                durable_event = await run_repo.append_event(
                    run_id,
                    event_type="error",
                    payload=error_payload,
                )
                await run_repo.mark_failed(run_id, str(exc))
                await session.commit()
                error_payload["sequence"] = durable_event.sequence
                await self._broker.publish(run_id, error_payload)

    async def get_run_events_after(
        self,
        *,
        run_id: uuid.UUID,
        after_sequence: int,
    ) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            run_repo = DurableRunRepo(session)
            events = await run_repo.list_events(run_id, after_sequence=after_sequence)

        replay: list[dict[str, Any]] = []
        for event in events:
            payload = dict(event.payload or {})
            payload.setdefault("type", event.event_type)
            payload["sequence"] = event.sequence
            payload["run_id"] = str(run_id)
            replay.append(payload)
        return replay

    async def submit_interrupt_response(
        self,
        request_id: str,
        response: dict[str, Any],
    ) -> bool:
        """Deliver *response* to the worker coroutine waiting on *request_id*.

        Returns True if a pending interrupt was found and resolved, False otherwise.
        """
        return await self._interrupt_store.resolve(request_id, response)

    async def get_run_status(self, run_id: uuid.UUID) -> str | None:
        async with self._session_factory() as session:
            run_repo = DurableRunRepo(session)
            run = await run_repo.get(run_id)
        return run.status if run else None


_background_worker: BackgroundRunWorker | None = None


def get_background_run_worker() -> BackgroundRunWorker:
    global _background_worker
    if _background_worker is None:
        _background_worker = BackgroundRunWorker(session_factory=get_session_factory())
    return _background_worker


async def shutdown_background_run_worker() -> None:
    global _background_worker
    if _background_worker is None:
        return
    await _background_worker.stop()
    _background_worker = None
