# Load the real anyio before dspy>=3.4 installs a lazy proxy for it, which breaks later anyio.abc imports.
import anyio  # noqa: F401
