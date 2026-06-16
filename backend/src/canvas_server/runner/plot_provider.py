"""Plot provider -- gives worker agents the ability to generate plots via Python code."""

import logging

from canvas_server.sandbox import get_sandbox

logger = logging.getLogger(__name__)


class PlotProvider:
    """Wraps SandboxManager to expose generate_plot tool function to agents."""

    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id

    async def generate_plot(self, python_code: str) -> str:
        """
        Generates a plot by executing the provided Python code in a sandboxed environment.
        The code MUST import either matplotlib.pyplot or plotly and call plt.show() or fig.show() to render the plot.
        The output figure will be captured and returned to the chat UI automatically.
        Do NOT save the plot to a file inside the code; always use the library's show() method.

        Args:
            python_code (str): The complete Python code script to execute.

        Returns:
            str: A JSON string containing the base64-encoded plot image(s) if successful, or an error message.
        """
        try:
            sandbox = await get_sandbox()
            # The session returned is now an ArtifactSandboxSession
            session = sandbox.get_session(self.conversation_id)

            logger.info("Executing plot code in sandbox...")
            result = session.run(python_code)

            if result.error:
                logger.error(f"Plot code execution error: {result.error}")
                return f"Error executing plot code: {result.error}\nStderr: {result.stderr}"

            # Extract plots
            plots_base64 = []
            if hasattr(result, "plots") and result.plots:
                for plot in result.plots:
                    plots_base64.append(plot.content_base64)

            if not plots_base64:
                return (
                    "Execution successful, but no plots were generated. "
                    f"Did you call plt.show() or fig.show()?\nStdout: {result.stdout}"
                )

            # For returning multiple images, we could format a JSON payload that the frontend understands,
            # but for DSPy tool response, we'll return a marker string that the frontend can parse,
            # or just return the base64 encoded string directly if it's one image.
            import json

            return json.dumps({
                "status": "success",
                "message": "Plot generated successfully. The UI will render this data.",
                "images_base64": plots_base64,
                "stdout": result.stdout
            })

        except Exception as e:
            logger.exception("generate_plot failed")
            return f"Error generating plot: {e}"
