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


class McpToolGrant(BaseModel):
    """One enabled tool of an MCP-backed Tool Node's grant (spec §2.1).

    The grant unit is ``(server reference, enabled-tools selection)`` (#119);
    approval granularity is per enabled tool (#119 Q9) — the node-level
    ``requires_approval`` boolean continues to govern author (code) tools only.
    """

    name: str
    requires_approval: bool

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("mcp_tools entry: name must not be empty")
        return trimmed


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
    # MCP variant (#132): non-null ⇒ MCP-backed node (code/args stay empty);
    # ``mcp_tools`` is the enabled-tools selection for the server grant.
    mcp_server_id: uuid.UUID | None = None
    mcp_tools: list[McpToolGrant] = Field(default_factory=list)


class ToolNodeResponse(ToolNodeInput):
    canvas_id: uuid.UUID


class AttachmentNodeBase(BaseModel):
    id: uuid.UUID
    name: str = "Attachment"
    file_type: str = "text"
    description: str = ""
    # Runtime consumption preference (#88): "inline" or "file_path". See
    # ``AttachmentNode.delivery_method`` for the full contract.
    delivery_method: str = "inline"
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

    @field_validator("delivery_method")
    @classmethod
    def validate_delivery_method(cls, v: str) -> str:
        trimmed = v.strip().lower()
        if trimmed not in ("inline", "file_path"):
            raise ValueError("delivery_method must be 'inline' or 'file_path'")
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


class ChatAttachmentUploadResult(BaseModel):
    filename: str
    success: bool
    attachment_id: uuid.UUID | None = None
    node_id: uuid.UUID | None = None
    file_type: str | None = None
    error: str | None = None


class ChatAttachmentUploadResponse(BaseModel):
    results: list[ChatAttachmentUploadResult]


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


# --- MCP server registry ---


class McpServerBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    # Endpoint URL; validated http(s):// on every write path (spec §5.1).
    url: str = Field(min_length=1, max_length=2083)
    credential_header: str | None = Field(default="Authorization", max_length=64)


class McpServerCreate(McpServerBase):
    # Omitted/None starts with no credential stored.
    credential_value: str | None = None


class McpServerUpdate(McpServerBase):
    # None keeps the stored credential; "" clears it (§3.1).
    credential_value: str | None = None


class McpServerResponse(McpServerBase):
    """The credential itself is never returned — only ``credential_set`` and a
    masked preview. ``url_warning`` surfaces the plain-http caveat (§5.1)."""

    id: uuid.UUID
    credential_set: bool
    credential_preview: str | None = None
    url_warning: str | None = None


class McpServerListResponse(BaseModel):
    servers: list[McpServerResponse]


# --- MCP connection probe (Settings "Test connection", #131) ---


class McpServerTestRequest(BaseModel):
    """Test-button request mirroring the provider Test-button convention.

    Every field is an unsaved-form override; omitted fields (None) fall back
    to the stored registration when ``server_id`` is given. ``credential_value
    = ""`` tests *without* a credential, mirroring the PUT ""-clears rule.
    """

    server_id: uuid.UUID | None = None
    url: str | None = Field(default=None, max_length=2083)
    credential_header: str | None = Field(default=None, max_length=64)
    credential_value: str | None = None


class McpServerTestResponse(BaseModel):
    """Probe response — never contains the credential (§5.4)."""

    ok: bool
    server_name: str | None = None
    server_version: str | None = None
    tools: list[str] = Field(default_factory=list)
    tool_count: int = 0
    latency_ms: int = 0
    detail: str
    classification: str | None = None
    protocol_revision: str | None = None


# --- Live tool catalog (the editor's checklist, #134, spec §6.3) ---


class McpCatalogTool(BaseModel):
    """One server-provided tool descriptor — exactly as the server serves it
    (name, description, input schema). No snapshot is stored anywhere; the
    editor renders its checklist and expandable schema rows from this."""

    name: str
    description: str | None = None
    input_schema: dict = Field(default_factory=dict)


class McpServerCatalogResponse(BaseModel):
    """Live-catalog read over the short-lived probe connection. An
    unreachable server is a structured ``ok=False`` response (honest error,
    never stale data) — not an HTTP error. Never contains the credential."""

    ok: bool
    server_id: uuid.UUID
    tools: list[McpCatalogTool] = Field(default_factory=list)
    server_name: str | None = None
    server_version: str | None = None
    latency_ms: int = 0
    detail: str
    classification: str | None = None
    protocol_revision: str | None = None
