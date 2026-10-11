from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from canvas_server.background_run_worker import BackgroundRunWorker
from canvas_server.database import get_session_factory
from canvas_server.mcp_config import get_mcp_servers, reset_mcp_servers_cache
from canvas_server.models.mcp import McpServer
from canvas_server.repos.conversation_repo import ConversationRepo
from canvas_server.repos.durable_run_repo import DurableRunRepo
from tests.test_mcp_redaction import ServerCache, make_server


class TestSendEventRedaction:
    """§5.4 (#140): one redaction pass at the worker's send_event choke point
    strips configured MCP credential values + endpoint URLs from every event
    payload bound for the durable log (DB replay, WS) and the broker (UI)."""

    async def test_event_payloads_are_redacted_before_persisting(
        self, blank_canvas, test_session, monkeypatch
    ):
        conversation_repo = ConversationRepo(test_session)
        conversation = await conversation_repo.create(blank_canvas.id, "Redaction Chat")
        run_repo = DurableRunRepo(test_session)
        run = await run_repo.create(conversation.id, prompt="leaky run")

        class FakeCoordinator:
            def __init__(self, *, session, conversation_repo, canvas_repo):
                pass

            async def run(
                self,
                *,
                conversation_id,
                user_prompt,
                send_event,
                target_agent_id=None,
                get_client_response=None,
                run_id=None,
            ):
                await send_event(
                    {
                        "type": "error",
                        "message": (
                            "ConnectError: auth failed for"
                            " https://mcp.corp.internal/sse"
                            " with key sk-corp-secret-123"
                        ),
                    }
                )

        monkeypatch.setattr(
            "canvas_server.background_run_worker.ConversationRunCoordinator",
            FakeCoordinator,
        )
        monkeypatch.setattr(
            "canvas_server.mcp_redaction.get_mcp_servers",
            ServerCache(
                make_server(
                    url="https://mcp.corp.internal/sse",
                    credential_value="sk-corp-secret-123",
                )
            ),
        )

        worker = BackgroundRunWorker(session_factory=get_session_factory())
        assert await worker.process_once() is True

        async with get_session_factory()() as session:
            events = await DurableRunRepo(session).list_events(run.id)

        assert "[REDACTED]" in events[0].payload["message"]
        assert "https://mcp.corp.internal/sse" not in events[0].payload["message"]
        assert "sk-corp-secret-123" not in events[0].payload["message"]

    async def test_run_level_error_payload_and_failure_reason_are_redacted(
        self, blank_canvas, test_session, monkeypatch
    ):
        # The catch-all error path builds its payload directly (not via
        # send_event) — it is redacted at the same seam boundary.
        conversation_repo = ConversationRepo(test_session)
        conversation = await conversation_repo.create(blank_canvas.id, "Boom Chat")
        run_repo = DurableRunRepo(test_session)
        run = await run_repo.create(conversation.id, prompt="exploding run")

        secret_fragment = "sk-corp-secret-123"
        endpoint = "https://mcp.corp.internal/sse"

        class FakeCoordinator:
            def __init__(self, *, session, conversation_repo, canvas_repo):
                pass

            async def run(
                self,
                *,
                conversation_id,
                user_prompt,
                send_event,
                target_agent_id=None,
                get_client_response=None,
                run_id=None,
            ):
                raise ConnectionError(
                    f"ConnectError: connect to {endpoint} failed"
                    f" (key {secret_fragment})"
                )

        monkeypatch.setattr(
            "canvas_server.background_run_worker.ConversationRunCoordinator",
            FakeCoordinator,
        )
        monkeypatch.setattr(
            "canvas_server.mcp_redaction.get_mcp_servers",
            ServerCache(
                make_server(url=endpoint, credential_value=secret_fragment)
            ),
        )

        worker = BackgroundRunWorker(session_factory=get_session_factory())
        assert await worker.process_once() is True

        async with get_session_factory()() as session:
            fresh_repo = DurableRunRepo(session)
            failed_run = await fresh_repo.get_or_404(run.id)
            events = await fresh_repo.list_events(run.id)

        assert failed_run.status == "failed"
        assert secret_fragment not in failed_run.final_error
        assert endpoint not in failed_run.final_error
        assert "[REDACTED]" in failed_run.final_error
        assert secret_fragment not in events[-1].payload["message"]
        assert endpoint not in events[-1].payload["message"]


class TestMcpRegistryRefreshOnClaim:
    """The durable-run worker is a separate process: its process-local
    ``mcp_config`` cache starts empty and no API write route ever runs in it.
    Claiming a run must refresh the MCP registry (mirroring
    ``refresh_provider_config``) or every MCP-backed tool node degrades with
    "server … is not registered" even though the row exists."""

    async def test_process_once_refreshes_mcp_servers_cache(
        self, blank_canvas, test_session, monkeypatch
    ):
        reset_mcp_servers_cache()
        test_session.add(McpServer(name="weather", url="http://mcp-weather:8000/mcp"))
        await test_session.commit()
        assert get_mcp_servers() == ()  # separate worker process starts cold

        conversation_repo = ConversationRepo(test_session)
        conversation = await conversation_repo.create(blank_canvas.id, "MCP Cache Chat")
        run_repo = DurableRunRepo(test_session)
        await run_repo.create(conversation.id, prompt="weather run")

        class FakeCoordinator:
            def __init__(self, *, session, conversation_repo, canvas_repo):
                pass

            async def run(
                self,
                *,
                conversation_id,
                user_prompt,
                send_event,
                target_agent_id=None,
                get_client_response=None,
                run_id=None,
            ):
                pass

        monkeypatch.setattr(
            "canvas_server.background_run_worker.ConversationRunCoordinator",
            FakeCoordinator,
        )

        try:
            worker = BackgroundRunWorker(session_factory=get_session_factory())
            assert await worker.process_once() is True
            # The claim re-read the registry before the run executed.
            assert [s.name for s in get_mcp_servers()] == ["weather"]
        finally:
            reset_mcp_servers_cache()


@pytest.mark.asyncio
async def test_worker_processes_queued_run_and_marks_completed(
    blank_canvas, test_session, monkeypatch
):
    conversation_repo = ConversationRepo(test_session)
    conversation = await conversation_repo.create(blank_canvas.id, "Worker Chat")

    run_repo = DurableRunRepo(test_session)
    run = await run_repo.create(conversation.id, prompt="run in background")

    class FakeCoordinator:
        def __init__(self, *, session, conversation_repo, canvas_repo):
            pass

        async def run(
            self,
            *,
            conversation_id,
            user_prompt,
            send_event,
            target_agent_id=None,
            get_client_response=None,
            run_id=None,
        ):
            await send_event({"type": "run_start"})
            await send_event({"type": "run_complete", "result": "ok"})

    monkeypatch.setattr(
        "canvas_server.background_run_worker.ConversationRunCoordinator",
        FakeCoordinator,
    )

    worker = BackgroundRunWorker(session_factory=get_session_factory())
    processed = await worker.process_once()

    assert processed is True

    async with get_session_factory()() as session:
        fresh_repo = DurableRunRepo(session)
        updated_run = await fresh_repo.get_or_404(run.id)
        events = await fresh_repo.list_events(run.id)

    assert updated_run.status == "completed"
    assert updated_run.attempt_count == 1
    assert [event.sequence for event in events] == [1, 2]
    assert events[0].event_type == "run_start"
    assert events[1].event_type == "run_complete"


@pytest.mark.asyncio
async def test_worker_reclaims_expired_running_lease(
    blank_canvas, test_session, monkeypatch
):
    conversation_repo = ConversationRepo(test_session)
    conversation = await conversation_repo.create(blank_canvas.id, "Recover Worker Chat")

    run_repo = DurableRunRepo(test_session)
    run = await run_repo.create(conversation.id, prompt="recover run")

    expired_lease = datetime.now(UTC) - timedelta(minutes=2)
    await run_repo.mark_running(
        run.id,
        lease_owner="old-worker",
        lease_expires_at=expired_lease,
    )
    await test_session.commit()

    class FakeCoordinator:
        def __init__(self, *, session, conversation_repo, canvas_repo):
            pass

        async def run(
            self,
            *,
            conversation_id,
            user_prompt,
            send_event,
            target_agent_id=None,
            get_client_response=None,
            run_id=None,
        ):
            await send_event({"type": "run_complete"})

    monkeypatch.setattr(
        "canvas_server.background_run_worker.ConversationRunCoordinator",
        FakeCoordinator,
    )

    worker = BackgroundRunWorker(session_factory=get_session_factory())
    processed = await worker.process_once()

    assert processed is True

    async with get_session_factory()() as session:
        fresh_repo = DurableRunRepo(session)
        updated_run = await fresh_repo.get_or_404(run.id)

    assert updated_run.status == "completed"
    assert updated_run.attempt_count == 2


@pytest.mark.asyncio
async def test_worker_marks_run_aborted_when_abort_requested_mid_execution(
    blank_canvas, test_session, monkeypatch
):
    conversation_repo = ConversationRepo(test_session)
    conversation = await conversation_repo.create(blank_canvas.id, "Abort Worker Chat")

    run_repo = DurableRunRepo(test_session)
    run = await run_repo.create(conversation.id, prompt="please abort")

    first_event_sent = asyncio.Event()
    continue_execution = asyncio.Event()

    class FakeCoordinator:
        def __init__(self, *, session, conversation_repo, canvas_repo):
            pass

        async def run(
            self,
            *,
            conversation_id,
            user_prompt,
            send_event,
            target_agent_id=None,
            get_client_response=None,
            run_id=None,
        ):
            await send_event({"type": "run_start"})
            first_event_sent.set()
            await continue_execution.wait()
            await send_event({"type": "thought", "agent": "Planner", "content": "late event"})

    monkeypatch.setattr(
        "canvas_server.background_run_worker.ConversationRunCoordinator",
        FakeCoordinator,
    )

    worker = BackgroundRunWorker(session_factory=get_session_factory())
    process_task = asyncio.create_task(worker.process_once())

    await first_event_sent.wait()

    async with get_session_factory()() as session:
        fresh_repo = DurableRunRepo(session)
        await fresh_repo.mark_aborting(run.id)
        await session.commit()

    continue_execution.set()
    processed = await process_task
    assert processed is True

    async with get_session_factory()() as session:
        fresh_repo = DurableRunRepo(session)
        updated_run = await fresh_repo.get_or_404(run.id)
        events = await fresh_repo.list_events(run.id)

    assert updated_run.status == "aborted"
    assert events[0].event_type == "run_start"
    assert events[-1].event_type == "run_aborted"


@pytest.mark.asyncio
async def test_worker_get_client_response_blocks_until_response_submitted(
    blank_canvas, test_session, monkeypatch
):
    """get_client_response awaits a future that is resolved when submit_interrupt_response is called."""
    from canvas_server.background_run_worker import InterruptStore

    store = InterruptStore()
    captured_response: dict = {}

    async def waiter():
        res = await store.wait_for_response("req-001")
        captured_response.update(res)

    wait_task = asyncio.create_task(waiter())
    await asyncio.sleep(0)  # yield to let waiter block

    assert not wait_task.done()

    resolved = await store.resolve("req-001", {"content": "hello human"})
    assert resolved is True

    await wait_task
    assert captured_response == {"content": "hello human"}


@pytest.mark.asyncio
async def test_worker_submit_interrupt_response_returns_false_for_unknown_request(
    blank_canvas, test_session, monkeypatch
):
    from canvas_server.background_run_worker import InterruptStore

    store = InterruptStore()
    resolved = await store.resolve("nonexistent-req", {"content": "oops"})
    assert resolved is False


@pytest.mark.asyncio
async def test_worker_passes_get_client_response_that_uses_interrupt_store(
    blank_canvas, test_session, monkeypatch
):
    """The worker's _execute_run passes a live get_client_response to the coordinator."""
    conversation_repo = ConversationRepo(test_session)
    conversation = await conversation_repo.create(blank_canvas.id, "Interrupt Chat")

    run_repo = DurableRunRepo(test_session)
    run = await run_repo.create(conversation.id, prompt="ask the human")

    response_received: dict = {}
    interrupt_request_id: list[str] = []

    class FakeCoordinator:
        def __init__(self, *, session, conversation_repo, canvas_repo):
            pass

        async def run(
            self,
            *,
            conversation_id,
            user_prompt,
            send_event,
            target_agent_id=None,
            get_client_response=None,
            run_id=None,
        ):
            assert get_client_response is not None, "get_client_response must not be None"

            # Simulate emitting human_input_request
            req_id = "interrupt-test-req-001"
            interrupt_request_id.append(req_id)
            await send_event({"type": "human_input_request", "request_id": req_id, "question": "What is your name?"})

            # Block waiting for the response
            res = await get_client_response(req_id, "human_input_response")
            response_received.update(res)

            await send_event({"type": "run_complete", "result": "done"})

    monkeypatch.setattr(
        "canvas_server.background_run_worker.ConversationRunCoordinator",
        FakeCoordinator,
    )

    worker = BackgroundRunWorker(session_factory=get_session_factory())
    process_task = asyncio.create_task(worker.process_once())

    # Wait for the human_input_request event to be emitted
    deadline = asyncio.get_event_loop().time() + 5
    while not interrupt_request_id and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.05)

    assert interrupt_request_id, "human_input_request was never emitted"

    # Wait for the future to be registered in the interrupt store before resolving
    req_id = interrupt_request_id[0]
    deadline = asyncio.get_event_loop().time() + 5
    while req_id not in worker._interrupt_store._pending and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.05)
    assert req_id in worker._interrupt_store._pending, "Interrupt future was never registered"

    # Submit the response via the worker's public interface
    submitted = await worker.submit_interrupt_response(
        interrupt_request_id[0], {"content": "I am the user"}
    )
    assert submitted is True

    processed = await asyncio.wait_for(process_task, timeout=5.0)
    assert processed is True
    assert response_received == {"content": "I am the user"}

    async with get_session_factory()() as session:
        fresh_repo = DurableRunRepo(session)
        updated_run = await fresh_repo.get_or_404(run.id)
    assert updated_run.status == "completed"


@pytest.mark.asyncio
async def test_worker_resumes_interrupt_from_durable_event_when_api_process_is_separate(
    blank_canvas, test_session, monkeypatch
):
    """Worker should consume interrupt_response durable events even without in-process submit."""
    conversation_repo = ConversationRepo(test_session)
    conversation = await conversation_repo.create(blank_canvas.id, "Durable Interrupt Chat")

    run_repo = DurableRunRepo(test_session)
    run = await run_repo.create(conversation.id, prompt="wait for durable response")

    response_received: dict = {}

    class FakeCoordinator:
        def __init__(self, *, session, conversation_repo, canvas_repo):
            pass

        async def run(
            self,
            *,
            conversation_id,
            user_prompt,
            send_event,
            target_agent_id=None,
            get_client_response=None,
            run_id=None,
        ):
            request_id = "durable-req-001"
            await send_event(
                {
                    "type": "human_input_request",
                    "request_id": request_id,
                    "question": "Need confirmation",
                }
            )

            response = await get_client_response(request_id, "human_input_response")
            response_received.update(response)
            await send_event({"type": "run_complete", "result": "done"})

    monkeypatch.setattr(
        "canvas_server.background_run_worker.ConversationRunCoordinator",
        FakeCoordinator,
    )

    worker = BackgroundRunWorker(session_factory=get_session_factory())
    process_task = asyncio.create_task(worker.process_once())

    # Wait until the request event is persisted.
    deadline = asyncio.get_event_loop().time() + 5
    while asyncio.get_event_loop().time() < deadline:
        async with get_session_factory()() as session:
            fresh_repo = DurableRunRepo(session)
            events = await fresh_repo.list_events(run.id)
        if any(e.event_type == "human_input_request" for e in events):
            break
        await asyncio.sleep(0.05)

    async with get_session_factory()() as session:
        fresh_repo = DurableRunRepo(session)
        await fresh_repo.append_event(
            run.id,
            event_type="interrupt_response",
            payload={
                "type": "human_input_response",
                "request_id": "durable-req-001",
                "content": "confirmed",
            },
        )
        await session.commit()

    processed = await asyncio.wait_for(process_task, timeout=5.0)
    assert processed is True
    assert response_received == {
        "type": "human_input_response",
        "request_id": "durable-req-001",
        "content": "confirmed",
    }


@pytest.mark.asyncio
async def test_worker_initializes_and_shuts_down_sandbox_pool(monkeypatch):
    from unittest.mock import MagicMock


    mock_manager = MagicMock()
    async def fake_initialize_pool():
        mock_manager.initialize_pool_called = True
    async def fake_shutdown():
        mock_manager.shutdown_called = True

    mock_manager.initialize_pool = fake_initialize_pool
    mock_manager.shutdown = fake_shutdown
    mock_manager.initialize_pool_called = False
    mock_manager.shutdown_called = False

    monkeypatch.setattr(
        "canvas_server.sandbox.SandboxManager.get",
        lambda: mock_manager,
    )

    worker = BackgroundRunWorker(session_factory=get_session_factory())

    async def fake_process_once():
        return False
    monkeypatch.setattr(worker, "process_once", fake_process_once)

    await worker.ensure_started()
    await asyncio.sleep(0.05)
    await worker.stop()

    assert mock_manager.initialize_pool_called is True
    assert mock_manager.shutdown_called is True

