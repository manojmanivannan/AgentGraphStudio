import asyncio
import base64
import logging
import os
import uuid
from functools import partial

from canvas_server.sandbox import bounded_session_work, get_sandbox

logger = logging.getLogger(__name__)


class PlotProvider:
    """Wraps SandboxManager to expose generate_plot tool function to agents."""

    def __init__(self, conversation_id: str, conversation_repo = None):
        self.conversation_id = conversation_id
        self.conversation_repo = conversation_repo

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
            str: A Markdown string containing the image link(s) to the
                 generated plot(s) if successful, an error message, or the
                 'sandbox busy' observation. Never raises.
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
        if hasattr(result, "plots") and result.plots:
            for plot in result.plots:
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
                    plot_record = await self.conversation_repo.save_plot(
                        conversation_id=conv_id,
                        content=plot_bytes,
                        format=ext,
                    )
                    markdown_links.append(f"![Plot](/api/plots/{plot_record.id})")
                else:
                    filename = f"{uuid.uuid4().hex}.{ext}"
                    filepath = os.path.join(plots_dir, filename)
                    with open(filepath, "wb") as f:
                        f.write(plot_bytes)
                    markdown_links.append(f"![Plot](/api/static/plots/{filename})")

        if not markdown_links:
            return (
                "Execution successful, but no plots were generated. "
                f"Did you call plt.show() or fig.show()?\nStdout: {result.stdout}"
            )

        # Combine stdout and markdown links
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
