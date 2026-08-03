import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from canvas_server.exceptions import DurableRunNotFoundError
from canvas_server.models.canvas import Conversation, DurableRun, DurableRunEvent

NON_TERMINAL_RUN_STATUSES = ("queued", "running", "aborting")


class DurableRunRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _eager_query(self):
        return select(DurableRun).options(
            selectinload(DurableRun.events),
            selectinload(DurableRun.conversation).selectinload(Conversation.canvas),
        )

    async def create(
        self,
        conversation_id: uuid.UUID,
        prompt: str,
        target_agent_id: uuid.UUID | None = None,
    ) -> DurableRun:
        run = DurableRun(
            conversation_id=conversation_id,
            prompt=prompt,
            target_agent_id=target_agent_id,
            status="queued",
            attempt_count=0,
            replay_cursor=0,
        )
        self.session.add(run)
        await self.session.commit()
        return await self.get_or_404(run.id)

    async def get(self, run_id: uuid.UUID) -> DurableRun | None:
        result = await self.session.execute(self._eager_query().where(DurableRun.id == run_id))
        return result.scalar_one_or_none()

    async def get_or_404(self, run_id: uuid.UUID) -> DurableRun:
        run = await self.get(run_id)
        if not run:
            raise DurableRunNotFoundError(f"Durable run {run_id} not found")
        return run

    async def list_for_conversation(self, conversation_id: uuid.UUID) -> list[DurableRun]:
        result = await self.session.execute(
            self._eager_query()
            .where(DurableRun.conversation_id == conversation_id)
            .order_by(DurableRun.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_latest_active_for_conversation(
        self,
        conversation_id: uuid.UUID,
    ) -> DurableRun | None:
        result = await self.session.execute(
            select(DurableRun)
            .where(DurableRun.conversation_id == conversation_id)
            .where(DurableRun.status.in_(NON_TERMINAL_RUN_STATUSES))
            .order_by(DurableRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def claim_next_runnable(
        self,
        *,
        lease_owner: str,
        lease_expires_at: datetime,
        now: datetime | None = None,
    ) -> DurableRun | None:
        current_time = now or datetime.now(UTC)

        candidate_query = (
            select(DurableRun.id)
            .where(
                sa.or_(
                    DurableRun.status == "queued",
                    sa.and_(
                        DurableRun.status == "running",
                        DurableRun.lease_expires_at.is_not(None),
                        DurableRun.lease_expires_at <= current_time,
                    ),
                )
            )
            .order_by(DurableRun.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )

        candidate_result = await self.session.execute(candidate_query)
        run_id = candidate_result.scalar_one_or_none()
        if run_id is None:
            return None

        run = await self.get_or_404(run_id)
        run.status = "running"
        run.attempt_count += 1
        run.lease_owner = lease_owner
        run.lease_expires_at = lease_expires_at
        if run.started_at is None:
            run.started_at = current_time
        await self.session.flush()
        return run

    async def heartbeat_lease(
        self,
        run_id: uuid.UUID,
        *,
        lease_owner: str,
        lease_expires_at: datetime,
    ) -> DurableRun:
        run = await self.get_or_404(run_id)
        if run.lease_owner != lease_owner:
            raise DurableRunNotFoundError(
                f"Durable run {run_id} is not owned by {lease_owner}"
            )

        run.lease_expires_at = lease_expires_at
        await self.session.flush()
        return run

    async def append_event(
        self,
        run_id: uuid.UUID,
        event_type: str,
        payload: dict | None = None,
    ) -> DurableRunEvent:
        max_sequence_result = await self.session.execute(
            select(sa.func.coalesce(sa.func.max(DurableRunEvent.sequence), 0)).where(
                DurableRunEvent.run_id == run_id
            )
        )
        next_sequence = int(max_sequence_result.scalar_one()) + 1

        event = DurableRunEvent(
            run_id=run_id,
            sequence=next_sequence,
            event_type=event_type,
            payload=payload or {},
        )
        self.session.add(event)

        run = await self.get_or_404(run_id)
        run.replay_cursor = next_sequence

        await self.session.flush()
        return event

    async def list_events(
        self,
        run_id: uuid.UUID,
        after_sequence: int = 0,
    ) -> list[DurableRunEvent]:
        result = await self.session.execute(
            select(DurableRunEvent)
            .where(DurableRunEvent.run_id == run_id)
            .where(DurableRunEvent.sequence > after_sequence)
            .order_by(DurableRunEvent.sequence)
        )
        return list(result.scalars().all())

    async def mark_running(
        self,
        run_id: uuid.UUID,
        lease_owner: str | None = None,
        lease_expires_at: datetime | None = None,
    ) -> DurableRun:
        run = await self.get_or_404(run_id)
        run.status = "running"
        run.attempt_count += 1
        run.lease_owner = lease_owner
        run.lease_expires_at = lease_expires_at
        if run.started_at is None:
            run.started_at = datetime.now(UTC)
        await self.session.flush()
        return run

    async def mark_completed(self, run_id: uuid.UUID, result: str | None = None) -> DurableRun:
        run = await self.get_or_404(run_id)
        run.status = "completed"
        run.final_result = result
        run.final_error = None
        run.completed_at = datetime.now(UTC)
        run.lease_owner = None
        run.lease_expires_at = None
        await self.session.flush()
        return run

    async def mark_failed(self, run_id: uuid.UUID, error_message: str) -> DurableRun:
        run = await self.get_or_404(run_id)
        run.status = "failed"
        run.final_result = None
        run.final_error = error_message
        run.failed_at = datetime.now(UTC)
        run.lease_owner = None
        run.lease_expires_at = None
        await self.session.flush()
        return run

    async def mark_aborting(self, run_id: uuid.UUID) -> DurableRun:
        run = await self.get_or_404(run_id)
        if run.status in {"completed", "failed", "aborted"}:
            return run
        run.status = "aborting"
        await self.session.flush()
        return run

    async def mark_aborted(
        self,
        run_id: uuid.UUID,
        *,
        reason: str | None = "Run aborted by user",
    ) -> DurableRun:
        run = await self.get_or_404(run_id)
        run.status = "aborted"
        run.final_result = None
        run.final_error = reason
        run.failed_at = datetime.now(UTC)
        run.lease_owner = None
        run.lease_expires_at = None
        await self.session.flush()
        return run
