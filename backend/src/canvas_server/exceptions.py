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


class LLMConfigurationError(Exception):
    """Raised when the LLM configuration is incorrect or cannot connect."""
    pass


class PythonSyntaxError(ToolCompilationError):
    """Raised when python code syntax is invalid."""
    pass


class PythonImportError(ToolCompilationError):
    """Raised when a python import fails or module is missing."""
    pass


class RAGEmbeddingError(Exception):
    """Raised when RAG embedding generation fails."""
    pass


