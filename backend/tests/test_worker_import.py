import subprocess
import sys


def test_worker_entrypoint_imports_in_fresh_interpreter():
    # dspy>=3.4 lazily proxies anyio in sys.modules; importing the worker before anyio crashed on a circular import.
    result = subprocess.run(
        [sys.executable, "-c", "import canvas_server.worker_main"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
