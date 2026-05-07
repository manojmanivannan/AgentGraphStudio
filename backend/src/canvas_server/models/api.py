import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AgentNodeInput(BaseModel):
    id: uuid.UUID
    name: str = "Agent"
    role: str = ""
    instructions: str = ""
    model_name: str = "ollama:llama3.1"
    position_x: float = 0
    position_y: float = 0


class AgentNodeResponse(AgentNodeInput):
    canvas_id: uuid.UUID


class ToolNodeInput(BaseModel):
    id: uuid.UUID
    name: str = "Tool"
    code: str = ""
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
