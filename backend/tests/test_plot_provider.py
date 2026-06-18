from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
from llm_sandbox.data import ExecutionResult, FileType, PlotOutput

from canvas_server.runner.plot_provider import PlotProvider


@pytest.mark.asyncio
async def test_plot_provider_success():
    """Test plot generation successfully saves files and returns markdown links."""
    mock_sandbox_manager = MagicMock()
    mock_session = MagicMock()
    mock_sandbox_manager.get_session.return_value = mock_session

    mock_plot = PlotOutput(format=FileType.PNG, content_base64="bW9ja19iYXNlNjRfZGF0YQ==")
    mock_result = ExecutionResult(
        exit_code=0,
        stdout="Plot generated",
        stderr="",
        plots=[mock_plot]
    )
    mock_session.run.return_value = mock_result

    with patch("canvas_server.runner.plot_provider.get_sandbox", new_callable=AsyncMock) as mock_get_sandbox, \
         patch("builtins.open", mock_open()) as mock_file, \
         patch("os.makedirs") as mock_makedirs:
        mock_get_sandbox.return_value = mock_sandbox_manager

        provider = PlotProvider(conversation_id="test_conv_id")
        result_str = await provider.generate_plot("import matplotlib.pyplot as plt; plt.show()")

        mock_get_sandbox.assert_called_once()
        mock_sandbox_manager.get_session.assert_called_once_with("test_conv_id")
        mock_session.__enter__.assert_called_once()
        mock_session.run.assert_called_once_with("import matplotlib.pyplot as plt; plt.show()")
        mock_session.__exit__.assert_called_once()

        mock_makedirs.assert_called_once()
        mock_file.assert_called_once()

        assert "Plot generated" in result_str
        assert "![Plot](/api/static/plots/" in result_str
        assert ".png" in result_str



@pytest.mark.asyncio
async def test_plot_provider_failure():
    """Test exit code failure returns a proper error message with stderr."""
    mock_sandbox_manager = MagicMock()
    mock_session = MagicMock()
    mock_sandbox_manager.get_session.return_value = mock_session

    mock_result = ExecutionResult(
        exit_code=1,
        stdout="",
        stderr="SyntaxError: invalid syntax",
        plots=[]
    )
    mock_session.run.return_value = mock_result

    with patch("canvas_server.runner.plot_provider.get_sandbox", new_callable=AsyncMock) as mock_get_sandbox:
        mock_get_sandbox.return_value = mock_sandbox_manager

        provider = PlotProvider(conversation_id="test_conv_id")
        result = await provider.generate_plot("invalid python code")

        assert "Error executing plot code (exit code 1)" in result
        assert "SyntaxError: invalid syntax" in result


@pytest.mark.asyncio
async def test_plot_provider_no_plots():
    """Test execution succeeds but no plots are generated warns the user."""
    mock_sandbox_manager = MagicMock()
    mock_session = MagicMock()
    mock_sandbox_manager.get_session.return_value = mock_session

    mock_result = ExecutionResult(
        exit_code=0,
        stdout="print('hello')",
        stderr="",
        plots=[]
    )
    mock_session.run.return_value = mock_result

    with patch("canvas_server.runner.plot_provider.get_sandbox", new_callable=AsyncMock) as mock_get_sandbox:
        mock_get_sandbox.return_value = mock_sandbox_manager

        provider = PlotProvider(conversation_id="test_conv_id")
        result = await provider.generate_plot("print('hello')")

        assert "no plots were generated" in result
        assert "print('hello')" in result


@pytest.mark.asyncio
async def test_plot_provider_exception():
    """Test exception during sandbox acquisition or run is caught gracefully."""
    with patch("canvas_server.runner.plot_provider.get_sandbox", side_effect=Exception("Connection failed")):
        provider = PlotProvider(conversation_id="test_conv_id")
        result = await provider.generate_plot("plt.show()")

        assert "Error generating plot: Connection failed" in result


@pytest.mark.asyncio
async def test_plot_provider_success_db():
    """Test plot generation successfully saves to database when conversation_repo is provided."""
    mock_sandbox_manager = MagicMock()
    mock_session = MagicMock()
    mock_sandbox_manager.get_session.return_value = mock_session

    mock_plot = PlotOutput(format=FileType.PNG, content_base64="bW9ja19iYXNlNjRfZGF0YQ==")
    mock_result = ExecutionResult(
        exit_code=0,
        stdout="Plot generated",
        stderr="",
        plots=[mock_plot]
    )
    mock_session.run.return_value = mock_result

    mock_repo = AsyncMock()
    mock_record = MagicMock()
    mock_record.id = "mocked-plot-uuid"
    mock_repo.save_plot.return_value = mock_record

    with patch("canvas_server.runner.plot_provider.get_sandbox", new_callable=AsyncMock) as mock_get_sandbox:
        mock_get_sandbox.return_value = mock_sandbox_manager

        provider = PlotProvider(conversation_id="8cf53a28-98cc-4d37-88eb-116dbec8e2cb", conversation_repo=mock_repo)
        result_str = await provider.generate_plot("import matplotlib.pyplot as plt; plt.show()")

        mock_get_sandbox.assert_called_once()
        mock_sandbox_manager.get_session.assert_called_once_with("8cf53a28-98cc-4d37-88eb-116dbec8e2cb")
        mock_session.__enter__.assert_called_once()
        mock_session.run.assert_called_once_with("import matplotlib.pyplot as plt; plt.show()")
        mock_session.__exit__.assert_called_once()

        mock_repo.save_plot.assert_called_once()
        assert "Plot generated" in result_str
        assert "![Plot](/api/plots/mocked-plot-uuid)" in result_str

