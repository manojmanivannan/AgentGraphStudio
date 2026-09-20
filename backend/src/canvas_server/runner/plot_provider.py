from __future__ import annotations

import asyncio
import base64
import logging
import os
import uuid
from functools import partial
from typing import TYPE_CHECKING

from canvas_server.runner.attachment_events import announce_attachment_produced
from canvas_server.sandbox import bounded_session_work, get_sandbox

if TYPE_CHECKING:
    from canvas_server.models.canvas import AttachmentInstance
    from canvas_server.repos.conversation_repo import ConversationRepo
    from canvas_server.runner.run_state import CanvasRunState

logger = logging.getLogger(__name__)


class PlotProvider:
    """Wraps SandboxManager to expose generate_plot tool function to agents.

    A produced plot is stored as an ``image``-typed ``AttachmentInstance``
    (source ``agent_output``) via the same storage call used by the
    output-extraction mechanism (#86), and announced through the same
    ``attachment_produced`` event/persisted-message path (#87) — see
    ``runner.attachment_events.announce_attachment_produced``. ``agent_id``/
    ``agent_name``/``run_state`` are optional so existing direct-construction
    call sites (and unit tests) keep working without wiring up a full run
    context; the announcement is simply skipped when they're absent.
    """

    def __init__(
        self,
        conversation_id: str | uuid.UUID,
        conversation_repo: ConversationRepo | None = None,
        agent_id: uuid.UUID | None = None,
        agent_name: str | None = None,
        run_state: CanvasRunState | None = None,
    ) -> None:
        self.conversation_id: str | uuid.UUID = conversation_id
        self.conversation_repo: ConversationRepo | None = conversation_repo
        self.agent_id: uuid.UUID | None = agent_id
        self.agent_name: str | None = agent_name
        # Held live (not snapshotted) — mirrors the `ask_human` tool pattern in
        # `agent_factory.py`, since a worker's tools may be built once during
        # eager setup and reused across many turns, each with a fresh
        # `send_event`/`run_id` refreshed onto this same `run_state` instance.
        self.run_state: CanvasRunState | None = run_state

    async def generate_plot(self, python_code: str) -> str:
        """
        Generates a plot by executing the provided Python code in a sandboxed environment.
        The code MUST import either matplotlib.pyplot or plotly and call plt.show() or fig.show() to render the plot.
        No other libraries are allowed.
        The output figure will be captured and returned to the chat UI automatically.
        Do NOT save the plot to a file inside the code; always use the library's show() method.

        The pool-acquire wait is bounded and every blocking sandbox call runs in
        a worker thread (same scaffold as ``CodeProvider.run_code``): a
        saturated pool surfaces as the 'busy' observation instead of raising a
        raw ``PoolExhaustedError`` after the pool's own 30s WAIT — which, under
        parallel handoffs, also blocked the event loop and froze the sibling
        agents' LLM streaming and the WebSocket.

        Args:
            python_code (str): The complete Python code script to execute.

        Returns:
            str: A plain confirmation that the plot was generated and
                 attached to the conversation (it renders automatically as an
                 image thumbnail — no markdown link needs to be included in
                 your final answer), an error message, or the 'sandbox busy'
                 observation. Never raises.
        """
        try:
            sandbox = await get_sandbox()
            # The session returned is now an ArtifactSandboxSession
            session = sandbox.get_session(self.conversation_id, enable_plotting=True)

            logger.info("Executing plot code in sandbox...")
            acquired, result = await bounded_session_work(
                session, partial(self._execute_plot_code, python_code)
            )
        except Exception as e:
            logger.exception("generate_plot failed")
            return f"Error generating plot: {e}"

        if not acquired:
            # Pool exhausted within the bounded wait — the shared 'busy'
            # observation the agent can reason over.
            return result

        if result.exit_code != 0:
            logger.error(f"Plot code execution error: {result.stderr}")
            return f"Error executing plot code (exit code {result.exit_code}):\n{result.stderr}"

        # Extract and save plots
        import canvas_server
        backend_root = os.path.dirname(os.path.dirname(os.path.dirname(canvas_server.__file__)))
        plots_dir = os.path.join(backend_root, "storage", "plots")
        os.makedirs(plots_dir, exist_ok=True)

        markdown_links = []
        stored_attachments: list[tuple[AttachmentInstance, str, str]] = []
        plots = result.plots if hasattr(result, "plots") and result.plots else []
        run_id = self.run_state.run_id if self.run_state else None
        for index, plot in enumerate(plots, start=1):
            ext = "png"
            if hasattr(plot, "format") and plot.format:
                ext = (
                    str(plot.format.value).lower()
                    if hasattr(plot.format, "value")
                    else str(plot.format).lower()
                )

            plot_bytes = base64.b64decode(plot.content_base64)
            if self.conversation_repo:
                conv_id = (
                    uuid.UUID(self.conversation_id)
                    if isinstance(self.conversation_id, str)
                    else self.conversation_id
                )
                name = "plot" if len(plots) == 1 else f"plot_{index}"
                original_filename = f"{name}_{uuid.uuid4().hex}.{ext}"
                plot_record = await self.conversation_repo.save_attachment(
                    conversation_id=conv_id,
                    content=plot_bytes,
                    format=ext,
                    file_type="image",
                    source="agent_output",
                    produced_by_run_id=run_id,
                    original_filename=original_filename,
                )
                stored_attachments.append((plot_record, name, original_filename))
            else:
                filename = f"{uuid.uuid4().hex}.{ext}"
                filepath = os.path.join(plots_dir, filename)
                with open(filepath, "wb") as f:
                    f.write(plot_bytes)
                markdown_links.append(f"![Plot](/api/static/plots/{filename})")

        if not markdown_links and not stored_attachments:
            return (
                "Execution successful, but no plots were generated. "
                f"Did you call plt.show() or fig.show()?\nStdout: {result.stdout}"
            )

        # Announce each stored attachment through the same event/persisted-
        # message path used by the post-loop output-extraction mechanism
        # (#86) — not a separate/duplicate code path (#87). Only possible
        # when the tool was wired with live run context (agent id + a
        # `run_state` to read the *current* turn's `send_event`/`run_id`
        # from — see the constructor docstring); direct-construction callers
        # (unit tests, the local-disk fallback below) simply skip this.
        if stored_attachments and self.run_state is not None and self.agent_id is not None:
            conv_id_for_event = (
                uuid.UUID(self.conversation_id)
                if isinstance(self.conversation_id, str)
                else self.conversation_id
            )
            for plot_record, name, original_filename in stored_attachments:
                await announce_attachment_produced(
                    send_event=self.run_state.send_event,
                    conversation_service=getattr(self.run_state, "conversation_service", None),
                    agent_name=self.agent_name or "Agent",
                    agent_id=self.agent_id,
                    attachment_id=plot_record.id,
                    name=name,
                    file_type="image",
                    source="agent_output",
                    conversation_id=conv_id_for_event,
                    run_id=run_id,
                    original_filename=original_filename,
                )

        if stored_attachments:
            names = ", ".join(f"'{name}'" for _, name, _ in stored_attachments)
            plural = "s" if len(stored_attachments) > 1 else ""
            result_str = (
                f"Plot{plural} generated successfully and attached to the "
                f"conversation: {names}."
            )
        else:
            # Legacy local-disk fallback (no conversation_repo wired) — the
            # image never became an AttachmentInstance, so there's nothing to
            # announce; the LLM still needs the direct link to surface it.
            result_str = "\n".join(markdown_links)
        if result.stdout and result.stdout.strip():
            result_str = f"{result.stdout.strip()}\n\n{result_str}"
        return result_str

    async def _execute_plot_code(self, python_code: str, session):
        """Run the plot code on the pooled session without blocking the loop.

        The shared scaffold (:func:`bounded_session_work`) has already acquired
        the session and owns the per-turn hold, so this only clears prior
        plots and runs the code — inside a worker thread.
        """

        def _blocking():
            if hasattr(session, "clear_plots"):
                try:
                    session.clear_plots()
                except Exception as e:  # noqa: BLE001 - clear must not fail the plot
                    logger.warning(f"Failed to clear plots in sandbox: {e}")
            return session.run(python_code)

        return await asyncio.to_thread(_blocking)
