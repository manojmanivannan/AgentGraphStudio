import uuid
from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, Field, field_validator, model_validator

# Curated common file_type categories (#76). The taxonomy is enum-plus-freeform:
# any of these are accepted, and so is any other non-empty custom string.
ATTACHMENT_FILE_TYPES = frozenset(
    {"csv", "json", "text", "python", "yaml", "image", "pdf", "binary"}
)


class AgentNodeBase(BaseModel):
    id: uuid.UUID
    name: str = "Agent"
    role: str = ""
    instructions: str = ""
    model_name: str = "ollama:llama3.1"
    agent_type: str = "worker"
    enable_plotting: bool = False
    enable_coding: bool = False
    enable_network: bool = False
    enable_hitl: bool = False
    enable_memory: bool = False
    enable_conversation_history: bool = False
    enable_rag: bool = False
    rag_chunk_size: int = 1000
    rag_top_k: int = 5
    is_entry_point: bool = False
    position_x: float = 0
    position_y: float = 0

    @model_validator(mode="after")
    def validate_plotting_for_workers_only(self) -> Self:
        if self.agent_type == "router" and self.enable_plotting:
            raise ValueError("Plotting is only supported for worker agents, not Router agents.")
        return self

    @model_validator(mode="after")
    def validate_coding_for_workers_only(self) -> Self:
        if self.agent_type == "router" and self.enable_coding:
            raise ValueError("Coding is only supported for worker agents, not Router agents.")
        return self

    @model_validator(mode="after")
    def validate_network_for_workers_only(self) -> Self:
        # enable_network is a per-worker session capability (#56): it routes
        # the worker's sandbox session to the networked pool and injects the
        # pip_install tool. Routers never get network sessions or pip_install.
        if self.agent_type == "router" and self.enable_network:
            raise ValueError(
                "Network is only supported for worker agents, not Router agents."
            )
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


class AttachmentNodeBase(BaseModel):
    id: uuid.UUID
    name: str = "Attachment"
    file_type: str = "text"
    description: str = ""
    position_x: float = 0
    position_y: float = 0

    @field_validator("file_type")
    @classmethod
    def validate_file_type(cls, v: str) -> str:
        # Enum-plus-freeform (#76): any curated category or custom string is
        # accepted, but it must not be blank once trimmed.
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("file_type must not be empty")
        return trimmed


class AttachmentNodeInput(AttachmentNodeBase):
    pass


class AttachmentNodeResponse(AttachmentNodeBase):
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
    attachments: list[AttachmentNodeInput] = Field(default_factory=list)


class CanvasNodesResponse(BaseModel):
    agents: list[AgentNodeResponse] = Field(default_factory=list)
    tools: list[ToolNodeResponse] = Field(default_factory=list)
    attachments: list[AttachmentNodeResponse] = Field(default_factory=list)


class CanvasSaveRequest(BaseModel):
    name: str = "Untitled Canvas"
    nodes: CanvasNodesInput = Field(default_factory=CanvasNodesInput)
    edges: list[EdgeInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_attachment_edge_wiring(self) -> Self:
        # Canvas-save-time wiring validation (#76/#80): attachment nodes may
        # only connect to agent nodes (produces/consumes); attachment<->tool
        # and attachment<->attachment edges are always rejected.
        agent_ids = {a.id for a in self.nodes.agents}
        tool_ids = {t.id for t in self.nodes.tools}
        attachment_ids = {a.id for a in self.nodes.attachments}

        for e in self.edges:
            source_is_attachment = e.source_node_id in attachment_ids
            target_is_attachment = e.target_node_id in attachment_ids
            if not source_is_attachment and not target_is_attachment:
                continue
            if source_is_attachment and target_is_attachment:
                raise ValueError(
                    f"Edge {e.id}: attachment-to-attachment connections are not allowed"
                )
            if e.source_node_id in tool_ids or e.target_node_id in tool_ids:
                raise ValueError(
                    f"Edge {e.id}: attachment-to-tool connections are not allowed"
                )
            other_id = e.target_node_id if source_is_attachment else e.source_node_id
            if other_id not in agent_ids:
                raise ValueError(
                    f"Edge {e.id}: attachment nodes may only connect to agent nodes"
                )
            # Attachment<->agent edges must be tagged with the produces/consumes
            # edge_type that expresses their direction (#76/#80) — an agent
            # producing into an attachment is "produces"; an attachment feeding
            # an agent is "consumes". Other edge_type values are rejected here.
            expected_edge_type = "consumes" if source_is_attachment else "produces"
            if e.edge_type != expected_edge_type:
                raise ValueError(
                    f"Edge {e.id}: attachment<->agent edges must use "
                    f"edge_type={expected_edge_type!r}, got {e.edge_type!r}"
                )
        return self


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
    tool: str | None = None
    args: dict[str, Any] | None = None
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


class ChangePasswordRequest(BaseModel):
    """Body for /auth/change-password: verify the current password, then set
    a new one (which revokes every other session for the user)."""
    current_password: str
    new_password: str


class SessionsRevokedResponse(BaseModel):
    """Number of sessions destroyed by logout-other-sessions (or implicitly by
    change-password). The calling session is never counted — it's kept alive."""
    revoked: int


# --- Provider settings ---


class ProviderSettingsBase(BaseModel):
    profile: str = "custom"
    llm_provider_type: str = "ollama"
    llm_base_url: str = ""
    llm_model: str = ""
    mem0_embedder_model: str = ""
    mem0_embedder_dimensions: int = Field(default=768, gt=0, le=16384)


class ProviderSettingsResponse(ProviderSettingsBase):
    """The API key itself is never returned — only whether one is stored."""
    api_key_set: bool
    source: str


class ProviderSettingsUpdate(ProviderSettingsBase):
    # None keeps the stored key; "" clears it.
    api_key: str | None = None
    # Required when mem0_embedder_dimensions changes: RAG chunks and memories
    # embedded at the old size become unusable and are purged.
    confirm_reindex: bool = False


class ProviderTestRequest(ProviderSettingsBase):
    api_key: str | None = None


class ProviderCheckResult(BaseModel):
    name: str
    ok: bool
    detail: str
    latency_ms: int


class ProviderTestResponse(BaseModel):
    ok: bool
    checks: list[ProviderCheckResult]
