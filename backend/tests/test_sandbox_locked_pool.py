"""Real-Docker regression tests for the locked (network_mode="none") default
sandbox pool (#54).

These verify the acceptance criteria that need a real container:
- Floor-package (matplotlib/plotly/numpy) tool compilation still works under the
  locked pool — no regression.
- Plotting (``generate_plot``) still works under the locked pool.
- A tool declaring a *non-floor* dependency fails gracefully under the locked
  pool (no network → ``pip install`` fails) — the call raises, which
  ``StreamingReAct.aforward`` feeds back to the agent as an observation
  (CLAUDE.md §12). Accepted behaviour, not a bug.

They use the session-scoped ``autouse_sandbox`` fixture, which builds the
baked-floor image and initialises the locked pool when Docker is available, and
skip gracefully otherwise (``@requires_docker``).
"""

import shutil
import uuid

import pytest

from canvas_server.exceptions import PythonImportError, ToolExecutionError
from canvas_server.runner.plot_provider import PlotProvider
from canvas_server.tool_factory import compile_tool_from_code

requires_docker = pytest.mark.skipif(
    not shutil.which("docker"), reason="Docker not installed"
)


@requires_docker
@pytest.mark.asyncio
async def test_floor_package_tool_runs_under_locked_pool():
    """A tool that imports only floor packages (numpy) compiles and executes
    under the locked (network_mode="none") pool — floor packages are baked into
    the image, so no runtime pip is needed."""
    code = "def total(arr):\n    import numpy as np\n    return int(np.array(arr).sum())"
    fn = await compile_tool_from_code("totaler", code)
    result = await fn(arr=[1, 2, 3, 4])
    assert result == 10


@requires_docker
@pytest.mark.asyncio
async def test_matplotlib_tool_runs_under_locked_pool():
    """matplotlib is a floor package baked into the image, so a tool importing
    it runs under the locked pool without runtime pip."""
    code = (
        "def version():\n"
        "    import matplotlib\n"
        "    return matplotlib.__version__"
    )
    fn = await compile_tool_from_code("mplver", code)
    result = await fn()
    assert isinstance(result, str) and result  # a real version string


@requires_docker
@pytest.mark.asyncio
async def test_generate_plot_works_under_locked_pool():
    """Plotting (generate_plot) still works under the locked pool — matplotlib
    is baked into the floor image, so the plot-detection path needs no network."""
    provider = PlotProvider(conversation_id=str(uuid.uuid4()))
    code = (
        "import matplotlib.pyplot as plt\n"
        "plt.plot([1, 2, 3, 4], [1, 4, 9, 16])\n"
        "plt.show()\n"
    )
    result = await provider.generate_plot(code)
    assert "![Plot]" in result


@requires_docker
@pytest.mark.asyncio
async def test_non_floor_dependency_fails_gracefully_under_locked_pool():
    """A tool declaring a non-floor dependency (requests) cannot pip-install it
    under network_mode="none". Compilation (a syntax check) still succeeds, but
    calling the tool raises — which the runner feeds back to the agent as an
    observation (CLAUDE.md §12). This is accepted behaviour, not a bug."""
    code = (
        "def name():\n"
        "    import requests\n"
        "    return requests.__name__\n"
    )
    # Compile succeeds: the syntax check does not import the dependency.
    fn = await compile_tool_from_code("reqs", code, dependencies=["requests"])
    # Calling it fails gracefully (pip install blocked by network_mode="none",
    # then the import fails) — the exception is catchable, never a crash, and
    # the runner feeds it back to the agent as an observation (CLAUDE.md §12).
    with pytest.raises((PythonImportError, ToolExecutionError)):
        await fn()
