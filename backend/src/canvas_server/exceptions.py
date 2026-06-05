class CanvasNotFoundError(Exception):
    pass


class ConversationNotFoundError(Exception):
    pass


class ToolCompilationError(Exception):
    pass


class InvalidEdgeError(Exception):
    pass


class ExecutionError(Exception):
    pass


class ToolExecutionError(Exception):
    """Raised when a tool fails during test execution (e.g. type coercion failure)."""
    pass
