# ADR 0006: Execution Worker Database Session Concurrency Safety

## Status

Accepted

## Context

When executing worker agents in parallel (using the `execute_parallel_agents` tool), multiple concurrent tasks emit events (thoughts, tool calls, handoffs) and messages simultaneously. The backend execution worker (`_execute_run` in `background_run_worker.py`) instantiates and shares a single SQLAlchemy `AsyncSession` across the entire run execution to maintain transaction boundaries.

However, SQLAlchemy `AsyncSession` is not thread-safe or coroutine-safe for concurrent database operations. Under highly concurrent orchestration workloads:
1. Multiple tasks would call `DurableRunRepo.append_event` concurrently. Each task would perform a `select max(sequence)` query and calculate the same next sequence number, leading to `UniqueViolationError: duplicate key value violates unique constraint "uq_durable_run_events_sequence"` upon flush.
2. Concurrent database flushes on the shared session would trigger `Session is already flushing` or asyncpg state corruption errors.
3. If one task triggered a database transaction abort (due to a unique constraint violation), any subsequent operations on the same session in other tasks would immediately fail with a `PendingRollbackError`.

Previously, an `asyncio.Lock` was used in `ConversationService.persist_message` to serialize message additions. However, this did not protect the `send_event` callback, which was called concurrently from parallel agent tasks and executed `append_event` and `session.commit()`.

## Considered Options

### 1. Separate Database Sessions for Concurrent Tasks
Create a new SQLAlchemy `AsyncSession` for each concurrent agent task.
- **Pros:** Completely isolates database operations, avoiding session sharing entirely.
- **Cons:** Breaks transaction boundary guarantees for the single durable run execution. Hard to coordinate run cursors and finalize the database status atomically. Leads to connection pool exhaustion when scaling parallel agent tasks.

### 2. Lock-Protected Shared Session
Retain the single shared `AsyncSession` but serialize all accesses to it across the entire execution scope using a session-level lock.
- **Pros:** Preserves a single execution transaction boundary, is easy to implement, guarantees sequence number ordering, and completely prevents concurrent session flushes.
- **Cons:** Locks serialize database operations, but since database operations represent only a small fraction of the execution time (most time is spent on network/LLM calls), this serialization does not impact performance.

## Decision

**Option 2: Lock-Protected Shared Session.**

We introduce a session-level lock (`session.db_lock = asyncio.Lock()`) attached directly to the shared `AsyncSession` object inside the background worker execution loop. All database operations performed during run execution must retrieve and acquire this lock to ensure serialization.

Specifically:
- In `background_run_worker.py`, the `send_event` callback retrieves `getattr(session, "db_lock", ...)` and wraps database queries, event appending, and `session.commit()` inside an `async with` block.
- In `ConversationService.persist_message`, the shared lock is fetched from the repository's session object (`getattr(self.conversation_repo.session, "db_lock", self._lock)`) and is used to serialize message persistence.

## Consequences

- **Concurrency Safety:** Parallel agents can safely run concurrent DSPy tasks, tool calls, and LLM calls. Any database persistence (messages or events) is serialized, eliminating `uq_durable_run_events_sequence` unique constraint violations and `Session is already flushing` errors.
- **Transactional Consistency:** Event sequence numbers are generated in a strict, lock-guaranteed chronological order.
- **Minimal Performance Impact:** Only the fast database insert/query operations are serialized. The slow LLM and tool executions continue to run concurrently.
- **Clean Architecture:** No constructor changes or complex lock passing across runner classes; the lock is naturally scoped to the database session lifecycle.
