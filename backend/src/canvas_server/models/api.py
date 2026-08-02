import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class AgentNodeBase(BaseModel):
    id: uuid.UUID
    name: str = "Agent"
    role: str = ""
    instructions: str = ""
    model_name: str = "ollama:llama3.1"
    agent_type: str = "worker"
    enable_plotting: bool = False
    enable_hitl: bool = False
    enable_memory: bool = False
    enable_conversation_history: bool = False
    enable_rag: bool = False
    rag_chunk_size: int = 1000
    is_entry_point: bool = False
    position_x: float = 0
    position_y: float = 0

    @model_validator(mode="after")
    def validate_plotting_for_workers_only(self) -> "AgentNodeBase":
        if self.agent_type == "router" and self.enable_plotting:
            raise ValueError("Plotting is only supported for worker agents, not Router agents.")
        return self


class AgentNodeInput(AgentNodeBase):
    pass


class AgentDocumentInput(BaseModel):
    id: uuid.UUID
    agent_node_id: uuid.UUID
    name: str
    content: str | None = None
    created_at: datetime | None = None
    path: str | None = None


class AgentDocumentResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentNodeResponse(AgentNodeBase):
    canvas_id: uuid.UUID


class ToolNodeInput(BaseModel):
    id: uuid.UUID
    name: str = "Tool"
    code: str = ""
    packages: str = ""
    dependencies: list[str] = Field(default_factory=list)
    args: list[dict] = Field(default_factory=list)
    requires_approval: bool = False
    position_x: float = 0
    position_y: float = 0


class ToolNodeResponse(ToolNodeInput):
    canvas_id: uuid.UUID


class EdgeInput(BaseModel):
    id: uuid.UUID
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID
    edge_type: str = "tool_access"


class EdgeResponse(EdgeInput):
    canvas_id: uuid.UUID


class CanvasNodesInput(BaseModel):
    agents: list[AgentNodeInput] = Field(default_factory=list)
    tools: list[ToolNodeInput] = Field(default_factory=list)


class CanvasNodesResponse(BaseModel):
    agents: list[AgentNodeResponse] = Field(default_factory=list)
    tools: list[ToolNodeResponse] = Field(default_factory=list)


class CanvasSaveRequest(BaseModel):
    name: str = "Untitled Canvas"
    nodes: CanvasNodesInput = Field(default_factory=CanvasNodesInput)
    edges: list[EdgeInput] = Field(default_factory=list)


class CanvasImportRequest(CanvasSaveRequest):
    documents: list[AgentDocumentInput] = Field(default_factory=list)


class CanvasResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime
    nodes: CanvasNodesResponse
    edges: list[EdgeResponse]

    model_config = {"from_attributes": True}


class CanvasListResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


class CreateCanvasRequest(BaseModel):
    name: str = "Untitled Canvas"


class CreateConversationRequest(BaseModel):
    name: str = "New Conversation"


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    agent_name: str | None = None
    node_id: uuid.UUID | None = None
    event_type: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: uuid.UUID
    canvas_id: uuid.UUID
    name: str
    status: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse] = []

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    id: uuid.UUID
    canvas_id: uuid.UUID
    name: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SendMessageRequest(BaseModel):
    prompt: str
    target_agent_id: uuid.UUID | None = None


class ToolInspectRequest(BaseModel):
    code: str
    dependencies: list[str] = Field(default_factory=list)


class ToolArgumentInfo(BaseModel):
    name: str
    type_hint: str = "str"
    default_value: str | None = None


class ToolInspectResponse(BaseModel):
    function_name: str
    arguments: list[ToolArgumentInfo]


class ToolTestRequest(BaseModel):
    code: str
    args: dict[str, str] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)


class ToolTestResponse(BaseModel):
    success: bool
    output: str
    execution_time_ms: float


# --- Auth request/response models ---


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    """Returned by register and login: the authenticated user."""
    user: UserResponse
