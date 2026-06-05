"""Routes for the tool inspection and testing API.

These endpoints are stateless -- they do not require a database session.
They accept Python code as input and return metadata or execution results.
"""

import logging

from fastapi import APIRouter, HTTPException

from canvas_server.exceptions import ToolCompilationError
from canvas_server.models.api import (
    ToolInspectRequest,
    ToolInspectResponse,
    ToolTestRequest,
    ToolTestResponse,
)
from canvas_server.tool_factory import execute_tool_code, inspect_tool_code

logger = logging.getLogger("canvas_server.routes.tools")

tools_router = APIRouter(prefix="/api/tools", tags=["tools"])


@tools_router.post("/inspect", response_model=ToolInspectResponse)
async def inspect_tool(body: ToolInspectRequest):
    """Inspect a Python tool function and return its argument metadata.

    Accepts a code string containing a Python function definition.
    Returns the function name and a list of arguments with type hints and
    default values.
    """
    logger.info("Inspecting tool code: %s chars, deps=%s", len(body.code), body.dependencies)
    try:
        return await inspect_tool_code("test_tool", body.code, dependencies=body.dependencies)
    except ToolCompilationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@tools_router.post("/test", response_model=ToolTestResponse)
async def test_tool(body: ToolTestRequest):
    """Execute a Python tool function with the provided arguments.

    Accepts a code string and a dictionary of argument values (strings).
    Coerces the string values to the correct Python types based on the
    function's type hints, then executes the function in the sandbox and
    returns the result.
    """
    logger.info("Testing tool code: %s chars, %d args, deps=%s", len(body.code), len(body.args), body.dependencies)
    return await execute_tool_code("test_tool", body.code, body.args, dependencies=body.dependencies)