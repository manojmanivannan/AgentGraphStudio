import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AgentNodeInput(BaseModel):
    id: uuid.UUID
    name: str = "Agent"
    role: str = ""
    instructions: str = ""
    model_name: str = "ollama:llama3.1"
    agent_type: str = "worker"
    position_x: float = 0
    position_y: float = 0


class AgentNodeResponse(AgentNodeInput):
    canvas_id: uuid.UUID


class ToolNodeInput(BaseModel):
    id: uuid.UUID
    name: str = "Tool"
    code: str = ""
    args: list[dict] = Field(default_factory=list)
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


class CanvasSaveRequest(BaseModel):
    name: str = "Untitled Canvas"
    nodes: CanvasNodesInput = Field(default_factory=CanvasNodesInput)
    edges: list[EdgeInput] = Field(default_factory=list)


class CanvasResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime
    nodes: CanvasNodesInput
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
