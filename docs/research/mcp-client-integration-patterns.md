# Remote MCP Tool Integration Patterns in Mainstream Agent Frameworks

> Research note (2026-10-11). This feeds the spec for letting Agent Nodes invoke tools from
> external MCP servers over Streamable HTTP (branch `mcp-tools`). It surveys how
> LangChain/LangGraph, OpenAI Agents SDK (Python), Anthropic Claude Agent SDK (Python),
> LlamaIndex, and Pydantic AI turn remote MCP servers into agent-loop tools.
> All claims are from primary sources (official docs + source code); there is no existing
> research-notes convention in this repo, so this file establishes `docs/research/`.
> Not committed to git.

---

## Summary

Every framework surfaces remote MCP tools the same macro way — the agent's tool list is
assembled from a `tools/list` call per server, with the server's JSON Schema handed largely
unmodified to the model — but they differ sharply on **collision handling**, **session
lifetime**, and **guardrails**:

1. **Name collisions.** Three of five frameworks *raise an error* on duplicates
   (OpenAI Agents SDK `UserError`, Pydantic AI `UserError`); the rest silently collide
   (LlamaIndex: last-registered tool wins, no warning; langchain-mcp-adapters: opt-in
   prefixing is the only mitigation). Two frameworks namespace by construction:
   OpenAI (`mcp_<server>__<tool>`, opt-in via `mcp_config={include_server_in_tool_names: True}`)
   and Claude Agent SDK (`mcp__<server>__<tool>`, always-on because the CLI engine does discovery).
   Prefixing is uniformly opt-in or always-on, never silently automatic.
2. **Connection lifetime.** Two families: (a) **long-lived, user-managed sessions** —
   OpenAI Agents SDK (`connect()`/`cleanup()` by the caller, sessions shared across agents and
   runs) and pre-v2 Pydantic AI (ref-counted re-entrant async context managers); vs
   (b) **per-request/sessionless transports** — langchain-mcp-adapters (new `ClientSession` per
   tool call by default; holding a session is opt-in), LlamaIndex (`BasicMCPClient` opens a
   fresh session + `initialize()` for *every* `tools/list` and `tools/call`), and Claude Agent
   SDK (the SDK opens no sessions at all — a bundled CLI subprocess owns them, either per
   `query()` or per persistent `ClaudeSDKClient`). All MCP integrations (except Claude Agent
   SDK's external-server path) are async-only; sync agents bridge by running the event loop
   internally (`agent.run_sync()` in Pydantic AI) or are absent entirely.
3. **Tool-list caching.** Explicit and configurable: OpenAI (`cache_tools_list=False` default,
   refresh per run), Pydantic AI v1/v2 (`cache_tools=True` default, invalidated on
   `notifications/tools/list_changed` and on exit — notification-driven refresh is the standout
   design). langchain-mcp-adapters and LlamaIndex have **no cache at all** — tools re-listed per
   load. Claude Agent SDK caches inside the CLI (discovery cache, opt-in via
   `MCP_DISCOVERY_CACHE=1`) and honors `list_changed` notifications there.
4. **Guardrails on untrusted MCP output.** Essentially none in the wire path anywhere — no
   framework truncates or sanitizes MCP tool content by default; OpenAI's opt-in
   `tool_output_trimmer` is the sole in-pipeline mechanism. Approval/HITL for MCP tools is
   opt-in in every framework: OpenAI (`require_approval="always"/per-tool`), Pydantic AI
   (`toolset.approval_required(...)` → `DeferredToolRequests`), LangGraph
   (`HumanInTheLoopMiddleware` / interrupt-on-config; elicitation interrupts on by default in
   the new `langchain.mcp`), Claude Agent SDK (`can_use_tool` + `allowed_tools` globs, hard
   output limits: 25k tokens / 50k chars), LlamaIndex (nothing MCP-specific; DIY via workflows).
   This mirrors the MCP spec itself, which pushes client-side confirmation but prescribes no
   mechanism.

The most constraining facts for AgentGraphStudio's spec: **dupes across servers must be either
error-prefixed or namespaced — no mainstream framework silently merges**; and the **spec needs
to decide explicitly between per-run sessions (simple, matches the per-run BackgroundRunWorker
model) and long-lived pooled sessions (matches the existing SandboxManager warm-pool mental
model, but requires session lifecycle + reconnection machinery like OpenAI's
`MCPServerManager`)**. Also note Pydantic AI's `cache_tools=True` + `list_changed`
notification invalidation is the pattern to copy for tool lists that must stay fresh across
the canvas auto-save / multi-run lifetime of a worker.

---

## Cross-cutting: what the MCP spec fixes

Facts that all frameworks inherit (spec version 2025-06-18; the 2025-11-25 transport/security
pages are materially the same on these points):

- **Streamable HTTP** uses one endpoint accepting POST (JSON-RPC request/notification/response)
  and GET (optional server→client SSE stream). Every request carries the negotiated
  `MCP-Protocol-Version` header; responses are `application/json` or `text/event-stream`
  ([transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)).
- **Sessions are optional and server-granted**: the server MAY return `Mcp-Session-Id` at
  initialize; the client MUST echo it on subsequent requests; on receiving HTTP 404 the client
  MUST re-initialize; clients SHOULD DELETE the endpoint to end a session. Servers MAY also be
  stateless (no session id). Session termination by the server surfaces as 404, not an error to
  the client ([transports §Session Management](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#session-management)).
- **Resumability**: servers MAY attach SSE event `id`s; a broken client GET with
  `Last-Event-ID` may be replayed *for that stream only* ([transports §Resumability](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#resumability-and-redelivery)).
- **Tool discovery** is an explicit paginated `tools/list`; a server declaring
  `tools.listChanged` SHOULD send `notifications/tools/list_changed`; the client then re-lists
  ([tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)).
- **Tool schema**: `name` is "Unique identifier for the tool" *within a server* (uniqueness is
  per-server, not global — hence cross-server collisions are a client-side problem);
  `inputSchema` is JSON Schema, `outputSchema`/`structuredContent` optional
  ([tools §Data Types](https://modelcontextprotocol.io/specification/2025-06-18/server/tools#data-types)).
- **Security**: the spec's warning that tools are model-controlled carries a **"SHOULD always be
  a human in the loop with the ability to deny tool invocations"** instruction to clients;
  clients "SHOULD … Validate tool results before passing to LLM"; servers "SHOULD … Sanitize
  tool outputs"; tool **annotations are untrusted unless from a trusted server**
  ([tools §Security Considerations](https://modelcontextprotocol.io/specification/2025-06-18/server/tools#security-considerations)).
  The security-best-practices page also flags a session-hijack + SSE-redelivery vector where a
  forged `notifications/tools/list_changed` "could lead to [the client ending] up with tools
  that they were not aware were enabled" — i.e., a stale/naive tool cache is itself an attack
  surface ([security best practices §Session Hijack Prompt Injection](https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices)).

---

## 1. LangChain / LangGraph — `langchain-mcp-adapters` → `langchain.mcp`

**Status.** The `langchain-mcp-adapters` repo is archived for new work: its README banners
"MCP support has moved into LangChain under the `langchain.mcp` namespace"
([README](https://github.com/langchain-ai/langchain-mcp-adapters); migration guide:
[docs.langchain.com/oss/python/migrate/langchain-mcp-adapters](https://docs.langchain.com/oss/python/migrate/langchain-mcp-adapters)). Facts below are from `main` of the adapters repo plus the new namespace's docs.

### Surfacing

- **Explicit per-load discovery, not auto-registration.** `load_mcp_tools(session)` calls
  `list_tools` with manual cursor pagination (`_list_all_tools`,
  [tools.py](https://raw.githubusercontent.com/langchain-ai/langchain-mcp-adapters/main/langchain_mcp_adapters/tools.py)).
  `MultiServerMCPClient.get_tools()` fans out one `asyncio.create_task(load_mcp_tools(...))`
  per server and `asyncio.gather`s them
  ([client.py](https://raw.githubusercontent.com/langchain-ai/langchain-mcp-adapters/main/langchain_mcp_adapters/client.py)).
- **Schema mapping is pass-through**: `StructuredTool(name=…, args_schema=tool.inputSchema, …)`
  — the MCP JSON Schema is handed to LangChain verbatim (LangChain accepts a plain dict for
  `args_schema`), with MCP `annotations`/`_meta` folded into tool `metadata`.
- **Name collisions: opt-in prefixing only, and no detection.** Default `tool_name_prefix=False`
  → raw server tool names pass through and two servers exporting `search` simply collide.
  With `tool_name_prefix=True` and a `server_name`, names become `f"{server_name}_{tool.name}"`
  (`"weather_search"` for weather's `search`). There is no `mcp__` format and no
  `sanitize_tool_name`. Crucially the prefix is bound only at the model layer — `call_tool`
  closes over the *unprefixed* native `tool.name`, so the MCP call itself is unchanged
  ([tools docs](https://docs.langchain.com/oss/python/langchain/mcp/tools)).

### Lifetime

- **Stateless per-call by default; the context-manager shortcut was removed.** As of 0.1.0,
  `MultiServerMCPClient` cannot be used as a context manager (`__aenter__` raises
  `NotImplementedError(ASYNC_CONTEXT_MANAGER_ERROR)`) — you either `await client.get_tools()`
  (which opens a new `ClientSession` per tool invocation) or explicitly pin:
  `async with client.session("math") as session: tools = await load_mcp_tools(session)`
  ([README](https://github.com/langchain-ai/langchain-mcp-adapters),
  [client.py](https://raw.githubusercontent.com/langchain-ai/langchain-mcp-adapters/main/langchain_mcp_adapters/client.py)).
- **Async-only.** The produced `StructuredTool` gets only `coroutine=` set; sync invocation
  raises (`StructuredTool does not support sync invocation.`,
  [structured.py](https://raw.githubusercontent.com/langchain-ai/langchain/master/libs/core/langchain_core/tools/structured.py)).
  LangGraph's async `ToolNode` is the intended execution path. In the successor namespace the
  same pattern is documented: tools "each time a tool is invoked … open the client, run the
  MCP call, and release it", and holding a session means keeping the adapter's context open
  ([connections](https://docs.langchain.com/oss/python/langchain/mcp/connections)).
- Transports: `stdio | sse | streamable_http` (aliases `http`, `streamable-http`) +
  `websocket`; `auth` is a generic `httpx.Auth` passthrough (the MCP SDK's
  `OAuthClientProvider` subclasses `httpx.Auth`, so an OAuth client plugs in there)
  ([sessions.py](https://raw.githubusercontent.com/langchain-ai/langchain-mcp-adapters/main/langchain_mcp_adapters/sessions.py)). In the new namespace auth is FastMCP-shaped:
  bearer string, `"oauth"`, or `httpx.Auth`, with optional `token_storage`
  ([auth](https://docs.langchain.com/oss/python/langchain/mcp/auth)).

### Caching / refresh

- **None in the adapter** — every `load_mcp_tools`/`get_tools` re-opens sessions and re-lists
  tools from scratch. The only `MAX_ITERATIONS` in the source is the listing-pagination cap
  (1000 pages), not an agent loop limit.
- The successor `langchain.mcp` adds **opt-in tool-list caching with three modes** — `use`
  (default: serve a cached list within the server's TTL hint), `refresh` (always fresh),
  `bypass` (skip cache) — and warns to "Isolate any cached responses per user, keyed off the
  verified identity" ([connections](https://docs.langchain.com/oss/python/langchain/mcp/connections)).

### Guardrails

- **No truncation/sanitization** of MCP content blocks (converted verbatim; `AudioContent`
  raises `NotImplementedError`). Errors instead become model-visible: default
  `handle_tool_errors=True` converts `CallToolResult(isError=True)` into a
  `ToolMessage(status="error")` "so the agent can self-correct instead of crashing the run";
  transport/session failures always raise.
- **HITL is composable, not built in**: a `ToolCallInterceptor` wraps every call (onion chain,
  may return a `ToolMessage`/`Command` instead of an MCP result — the documented extension
  point for gating) ([interceptors.py](https://raw.githubusercontent.com/langchain-ai/langchain-mcp-adapters/main/langchain_mcp_adapters/interceptors.py)).
  In the successor namespace, `HumanInTheLoopMiddleware` + `InterruptOnConfig(when=needs_approval)`
  pauses the run for approve/reject, and **MCP elicitation requests surface as a LangGraph
  `interrupt()` and are on by default** (caveat: "Resuming reruns the tool from the beginning")
  ([migration guide](https://docs.langchain.com/oss/python/migrate/langchain-mcp-adapters)).
- **Loop limits are one layer out**: LangChain v1 prebuilt `ToolCallLimitMiddleware(tool_name,
  thread_limit, run_limit, exit_behavior="continue"|"error"|"end")` applies to any tools
  including MCP ones, and LangGraph has `recursion_limit`
  ([middleware reference](https://reference.langchain.com/python/langchain/agents/middleware/tool_call_limit/ToolCallLimitMiddleware)).

---

## 2. OpenAI Agents SDK (Python) — `openai-agents`

Primary: [official MCP docs](https://openai.github.io/openai-agents-python/mcp/) and
[src/agents/mcp (main)](https://github.com/openai/openai-agents-python/tree/main/src/agents/mcp) (`server.py`, `util.py`, `manager.py`); verified against `main`.

### Surfacing

- **Per-run listing.** "Every agent run calls `list_tools()` on each MCP server"
  ([docs](https://openai.github.io/openai-agents-python/mcp/)); `Agent.get_mcp_tools()` routes
  through `MCPUtil.get_all_function_tools(self.mcp_servers, …)` every time tools are needed,
  and `agent.py`'s `mcp_servers` docstring says tools from these servers are included per run
  ([agent.py](https://github.com/openai/openai-agents-python/blob/main/src/agents/agent.py)).
- **Schema → Responses tool mapping** happens in
  [util.py](https://github.com/openai/openai-agents-python/blob/main/src/agents/mcp/util.py) (`MCPUtil.to_function_tool`):
  - Ensures `schema["properties"] = {}` when absent — "MCP spec doesn't require the inputSchema
    to have `properties`, but OpenAI spec does."
  - `convert_schemas_to_strict` (agent `mcp_config` flag, default **False**) runs
    `ensure_strict_json_schema` — a best-effort transform that adds
    `additionalProperties: False`, forces all object properties `required`, rewrites `oneOf` →
    `anyOf`, unwinds `$ref` — and on failure logs "Error converting MCP schema to strict mode"
    and serves the original non-strict schema
    ([strict_schema.py](https://github.com/openai/openai-agents-python/blob/main/src/agents/strict_schema.py)).
- **Name collisions: hard error by default; opt-in namespacing.** Across servers the util
  tracks a `tool_names` set in iteration order and raises
  `UserError("Duplicate tool names found across MCP servers: …")`, with the unprefixed path's
  hint telling you to "Pass `include_server_in_tool_names=True` … to prefix tool names with
  their server name and avoid collisions." With `mcp_config={'include_server_in_tool_names':
  True}` public names become `mcp_{server}__{tool}`, ASCII-sanitized, capped at 64 chars with
  an 8-char SHA-1 hash suffix inserted when the base still collides or hits a reserved name
  (reserved names are built from the agent's own `FunctionTool`s and handoff tool names), and
  "the SDK still invokes the original MCP tool name on the original server."
- **`use_consistent_naming` does not exist** in this SDK — code search over the repo returns
  zero hits; the real flag is `include_server_in_tool_names`. Likewise there is no
  `iter_over_mcp_servers` and no per-server `get_tool` in the mcp module.

### Lifetime

- **Long-lived, user-managed sessions — explicitly not per-run.** From `agent.py` docstring:
  > "NOTE: You are expected to manage the lifecycle of these servers. Specifically, you must
  > call `server.connect()` before passing it to the agent, and `server.cleanup()` when the
  > server is no longer needed. Consider using `MCPServerManager` … to keep connect/cleanup in
  > the same task."
  Internally `connect()` enters an `AsyncExitStack`, builds the transport, creates a real
  `mcp.ClientSession(...)`, `await session.initialize()`, and keeps `self.session` set until
  `cleanup()`; `list_tools()` raises `UserError("Server not initialized. Make sure you call
  `connect()` first.")` otherwise. The same server instances are intended to be shared across
  agents/runs
  ([server.py](https://github.com/openai/openai-agents-python/blob/main/src/agents/mcp/server.py)).
- **`MCPServerManager`** is the bulk lifecycle helper: `connect_all`, `reconnect(failed_only=…)`,
  `cleanup_all`, `active_servers`/`failed_servers`, `drop_failed_servers=True` default,
  serialized ops, 10 s default connect/cleanup timeouts
  ([manager.py](https://github.com/openai/openai-agents-python/blob/main/src/agents/mcp/manager.py)).
  Servers also work as `async with server:`. (Hosted MCP — `HostedMCPTool` — is different: the
  Responses API owns the remote connection.)
- All integrations are fully async (`ClientSession`, coroutine tools); the SDK's overall run
  machinery is async-native, so no sync bridging exists or is needed at this layer.

### Caching / refresh

- **`cache_tools_list: bool = False`** on every transport class: "If `False`, the tools list
  will be fetched from the server on each call to `list_tools()`" — which, given per-run
  listing, means MCP tools are effectively **re-fetched per interaction unless caching is
  turned on**. With `True`, the list is fetched once; invalidation is a manual
  `invalidate_tools_cache()` call on the server (`_tools_cache_generation += 1;
  _cache_dirty = True`). Cache reads are generation-guarded and deep-copied snapshots so
  callers can't mutate the cache; listing auto-paginates through `nextCursor` (loop detection
  raises on a repeated cursor; optional `max_list_pages` bound) and never caches a partial list
  ([server.py](https://github.com/openai/openai-agents-python/blob/main/src/agents/mcp/server.py)).

### Guardrails

- **No truncation, no max-output-length, no sanitization of MCP tool results** — text content
  is returned to the model verbatim; images become base64 data URLs; `structuredContent`
  (opt-in `use_structured_content=True`) is serialized via `json.dumps`. An opt-in
  `tool_output_trimmer` extension exists but is not applied to MCP by default
  ([tool_output_trimmer.py](https://github.com/openai/openai-agents-python/blob/main/src/agents/extensions/tool_output_trimmer.py)).
- **Tool failures** go through `failure_error_function` (default returns the generic
  "An error occurred while running the tool. Please try again." — exception text is *not*
  exposed by default; `None` re-raises).
- **Approval for MCP tools: opt-in per server** via `require_approval` — `"always"`/`"never"`,
  bool, per-tool dict (`{"delete_file": "always", "read_file": "never"}`), grouped object, or a
  callable `(run_context, agent, tool) → bool` (callable policy with no agent is fail-closed →
  approval required). This lowers onto the same HITL interrupt machinery used for function
  tools (`ToolApprovalItem`), and approval state survives pause/resume (RunState serializes MCP
  approval requests). Server-level `tool_input_guardrails` / `tool_output_guardrails` (run
  "before the SDK sends that result back to the model") are the other knobs.
- Docs security note: "MCP tools can expose data … with the credentials you provide. Connect
  only to servers you trust, use least-privilege credentials, keep access tokens in
  authorization fields or headers rather than URLs, and require approval for sensitive
  operations" ([mcp docs](https://openai.github.io/openai-agents-python/mcp/)).

### Transports & limits

`MCPServerStdio`, `MCPServerSse` (legacy — "The MCP project has deprecated the Server-Sent
Events transport"), `MCPServerStreamableHttp`; shared knobs `client_session_timeout_seconds=5`
(read timeout), `max_retry_attempts` / `retry_backoff_seconds_base|max`, `tool_filter`,
`cache_tools_list`, `max_list_pages`. The loop bound is `max_turns` (`DEFAULT_MAX_TURN = 10`,
`MaxTurnsExceeded`) — nothing MCP-specific.

---

## 3. Anthropic Claude Agent SDK (Python) — `claude-agent-sdk`

Primary: [types.py on main](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/types.py) (SDK 0.2.x), [`_internal/transport/subprocess_cli.py`](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/transport/subprocess_cli.py), [`_internal/sdk_mcp_bridge.py`](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/sdk_mcp_bridge.py), and docs at [code.claude.com](https://code.claude.com/docs/en/agent-sdk/mcp) + [MCP reference](https://code.claude.com/docs/en/mcp).

### Surfacing

- **The SDK does no tool discovery or mapping of its own — it serializes configs to the CLI.**
  `mcp_servers: dict[str, McpServerConfig] | str | Path` (default `{}`); the transport layer
  builds `["--mcp-config", json.dumps({"mcpServers": servers_for_cli})]`. All MCP networking,
  handshake, `tools/list`, reconnection, and retries happen inside the bundled Claude Code CLI
  subprocess
  ([subprocess_cli.py](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/transport/subprocess_cli.py)).
- **`McpServerConfig` variants** ([types.py](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/types.py)):
  `McpStdioServerConfig {command, args?, env?}`, `McpSSEServerConfig {type:"sse", url, headers?}`
  (deprecated), `McpHttpServerConfig {type:"http", url, headers?}`, and
  `McpSdkServerConfig {type:"sdk", name, instance}` for in-process servers. Streamable HTTP is
  `{"type": "http", "url": …, "headers": {…}}`; `"streamable-http"` is accepted as an alias in
  JSON config files only, and docs recommend against SSE servers
  ([mcp docs](https://code.claude.com/docs/en/agent-sdk/mcp#http-sse-servers)).
- **Discovery/naming is CLI-side and namespaced by construction**: tools appear in the `system`
  init message's `tools` array as `mcp__<server-name>__<tool-name>` (e.g. `mcp__github__list_issues`);
  the `mcp_servers` dict key becomes the `{server_name}` segment
  ([mcp docs](https://code.claude.com/docs/en/agent-sdk/mcp#allow-mcp-tools)).
- **Collision handling**: because every tool is `mcp__{server}__{tool}`, duplicates are
  namespaced away; between *scopes* (same server name from user/project/plugin config) the CLI
  resolves by precedence rather than merging; reserved server names are rejected. What happens
  when two servers legitimately expose the same `mcp__github__list_issues` after naming is
  **not documented** — the docs "contain no text addressing what happens when two different
  servers expose a tool with the same name"
  ([mcp reference](https://code.claude.com/docs/en/mcp)).
- Claude Code's **tool-search mode is on by default for Agent SDKs**: tool *definitions* are
  deferred and loaded on demand, up to a 10,000-tool catalog
  ([tool search](https://code.claude.com/docs/en/agent-sdk/tool-search)).

### Lifetime

- **The Python SDK never holds MCP sessions for external servers** — connection lifetime is a
  property of the CLI process. `query()` creates a new session (new CLI process → fresh MCP
  connections per call); `ClaudeSDKClient` reuses the same session, so MCP connections live as
  long as the client
  ([python reference](https://code.claude.com/docs/en/agent-sdk/python)).
- Only in-process (`"sdk"`) servers are bridged by the SDK through a control channel
  (`SdkMcpBridge`, one per `Query` lifetime).
- Programmatic connection control exists **only on the streaming client**:
  `reconnect_mcp_server(name)` (raises on failure), `toggle_mcp_server(name, enabled)`
  ("Disabling a server disconnects it and removes its tools from the available tool set"),
  `get_mcp_status()` → per-server `{status: connected|failed|needs-auth|pending|disabled,
  tools: McpToolInfo[], error, …}`
  ([client.py](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/client.py)).
- Resilience is CLI-side: dropped remote servers auto-reconnect with exponential backoff (up to
  5 attempts, 1 s doubling); first-connection transient errors retry 3×; env knobs
  `MCP_TIMEOUT` (30 s default), `MCP_TOOL_TIMEOUT`, `MCP_CONNECTION_NONBLOCKING`, etc.
  ([mcp reference](https://code.claude.com/docs/en/mcp)).

### Caching / refresh

- **Everything is CLI-side**: in SDK/non-interactive mode the CLI honors
  `notifications/tools/list_changed` by "refresh[ing] only the tool list on these
  notifications. If a refresh request fails, Claude Code keeps the server's previously
  discovered tools … until a later refresh succeeds."
- An **opt-in discovery cache** (`MCP_DISCOVERY_CACHE=1`, v2.1.221+) persists tool lists across
  sessions; CLI connections with a cached list don't block the first turn.
- The Python SDK exposes no cache/refresh API; its only levers are the streaming-client
  methods above ([mcp reference](https://code.claude.com/docs/en/mcp)).

### Guardrails

- **Explicit prompt-injection guidance, plus hard output limits — the strongest of the five.**
  - Trust warning: "Verify you trust each server before connecting it. Servers that fetch
    external content can expose you to prompt injection risk."
    ([mcp reference](https://code.claude.com/docs/en/mcp)).
  - **Output limits** ([mcp reference / MCP output limits](https://code.claude.com/docs/en/mcp)):
    results over **25,000 tokens** (`MAX_MCP_OUTPUT_TOKENS`, default 25,000) are persisted to a
    file and replaced in-conversation with an error naming the path; warning at >10,000 tokens;
    successful text results over **50,000 characters** are persisted unless the server declares
    `_meta["anthropic/maxResultSizeChars"]` (hard ceiling 500,000); error outputs > ~11,000
    chars are truncated to first/last 5,000 with an elision marker; a 16 MB decompressed
    response read cap exists.
  - **Permissions**: MCP tools "require explicit permission before Claude can use them";
    pre-approve via `allowed_tools=["mcp__github__*"]` (globs allowed only after a literal
    `mcp__<server>__` prefix), deny via `disallowed_tools` (deny rules hold even in
    `bypassPermissions`). `can_use_tool` is the callback that fires when CLI permission rules
    evaluate to "ask" — it is *not* called for calls already permitted by `allowed_tools`, so
    hard gating of untrusted servers must use deny rules or a `PreToolUse` hook. There is **no
    `mcp_tool_use` handler** in the Python SDK (that concept doesn't exist there); `@tool` /
    `create_sdk_mcp_server` builds *in-process* servers rather than intercepting remote ones
    ([mcp docs](https://code.claude.com/docs/en/agent-sdk/mcp#allow-mcp-tools),
    [agent-sdk security](https://code.claude.com/docs/en/security#mcp-security)).

---

## 4. LlamaIndex — `McpToolSpec` / `BasicMCPClient`

Primary: [`llama_index/tools/mcp/base.py`](https://github.com/run-llama/llama_index/blob/main/llama-index-integrations/tools/llama-index-tools-mcp/llama_index/tools/mcp/base.py), [`client.py`](https://github.com/run-llama/llama_index/blob/main/llama-index-integrations/tools/llama-index-tools-mcp/llama_index/tools/mcp/client.py), [official module guide](https://developers.llamaindex.ai/python/framework/module_guides/mcp/llamaindex_mcp/). Verified by grepping every PyPI release 0.1.0 → 0.6.0.

**Premise correction.** The brief's `allowed_tool_name_regex`, `tool_name_mapping`, a per-call
`asyncio.open_session`, and an `McpOauthToolSpec` class **do not exist** — zero GitHub or
PyPI-sdist hits in any release. The real filters are `allowed_tools: Optional[List[str]]`
(exact names) and OAuth is a client factory `BasicMCPClient.with_oauth(...)`. Any spec built
from LlamaIndex should cite the real API.

### Surfacing

- **Explicit list at spec-conversion time**: `to_tool_list_async()` → `fetch_tools()` →
  `await self.client.list_tools()` + exact-name `allowed_tools` filter (note the trap: an
  **empty list returns zero tools by design**, only `None` = all). Each tool's `input_schema`
  is converted JSON-Schema → pydantic via `create_model_from_json_schema`
  (`string→str`, `enum→Literal`, `anyOf→Union`, `$ref→nested models`, optional fields widened
  through `type | None`) and wrapped as `FunctionTool.from_defaults(..., tool_metadata=…)`.
- **No namespacing or collision handling at all**, and it's user-hostile: names pass through
  verbatim, and core's resolver is a silent **last-wins dict**
  (`tools_by_name = {tool.metadata.name: tool for tool in tools}` —
  [calling.py](https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/tools/calling.py)).
  Two servers exporting `search` → only the later-registered one is ever invoked, with no
  warning anywhere. The intended knob is manual renaming/partial-params by the user.

### Lifetime

- **A brand-new MCP session per API call** — `BasicMCPClient` subclasses `mcp.ClientSession`
  but is a config holder; every `call_tool`, `list_tools`, `read_resource`, … runs
  `async with self._run_session() as session: …`, which builds the transport
  (`streamable_http_client` default; `sse_client` if URL ends `/sse`; `stdio_client`),
  creates a `ClientSession`, and `await session.initialize()` **every time**
  ([client.py](https://github.com/run-llama/llama_index/blob/main/llama-index-integrations/tools/llama-index-tools-mcp/llama_index/tools/mcp/client.py)).
  For stdio servers this spawns a fresh subprocess per call; for HTTP servers only the shared
  `httpx.AsyncClient` is reused. There is no persistent-session option. OAuth tokens live on
  the client object via `with_oauth(...)`'s `TokenStorage` (default in-memory —
  `"Tokens will be lost on restart."` warning).

### Caching / refresh

- **None.** `to_tool_list_async` unconditionally re-fetches `tools/list` (over a fresh session).
  The only cache, `self.properties_cache`, memoizes generated pydantic model classes from
  JSON-Schema `$defs` across repeated spec conversions — not the tool list.

### Guardrails

- **Nothing MCP-specific.** `str(CallToolResult)` is the output-to-model fallback (pydantic
  repr, no truncation/size limit/sanitization/injection warnings). Exceptions caught in
  `calling.py` become `ToolOutput(is_error=True, content="Encountered error: …")`. HITL is a
  DIY workflow pattern (`HumanResponseEvent` / `InputRequiredEvent`) the tool itself must
  implement; the MCP tools have no `Context` plumbing, so it doesn't apply out of the box.
- Agentic-loop protection is agent-side: `FunctionAgent(..., max_iterations=…)` with
  `DEFAULT_MAX_ITERATIONS = 20`
  ([base_agent.py](https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/agent/workflow/base_agent.py)).

---

## 5. Pydantic AI — `MCPServer` (v1, deprecated) → `MCPToolset` (v2, current)

**Version reality check: Pydantic AI is on v2.x (2.55.0 at time of writing), and the old
`MCPServer*` classes were removed in v2.** The `tool_prefix` / `MCPServerStreamableHTTP` API
the task brief mentions belongs to the deprecated v1 line (last release 1.107.7). Both are
documented here because designs still reference the v1 API. Sources:
[v1 mcp.py @v1.107.7](https://raw.githubusercontent.com/pydantic/pydantic-ai/v1.107.7/pydantic_ai_slim/pydantic_ai/mcp.py),
[v2 mcp.py @v2.55.0](https://raw.githubusercontent.com/pydantic/pydantic-ai/v2.55.0/pydantic_ai_slim/pydantic_ai/mcp.py),
[v1 docs client.md](https://raw.githubusercontent.com/pydantic/pydantic-ai/v1.107.7/docs/mcp/client.md),
[current docs](https://pydantic.dev/docs/ai/mcp/overview/).

### Surfacing

- **No auto-registration at connect time in either version.** Servers go into
  `Agent(model, toolsets=[server])`; tools are discovered lazily **per run** via the toolset's
  `get_tools(ctx)` — `__aenter__`/`__aexit__` manage only the connection. In v2 the equivalent
  is `MCPToolset` (fastmcp-based; `toolsets=` unchanged).
- **JSON-Schema is pass-through**: `ToolDefinition(name=…, description=…,
  parameters_json_schema=mcp_tool.inputSchema, return_schema=mcp_tool.outputSchema …)`
  ([v1 mcp.py](https://raw.githubusercontent.com/pydantic/pydantic-ai/v1.107.7/pydantic_ai_slim/pydantic_ai/mcp.py)).
  v2 adds validation via a `TypeAdapter` and MCP-SDK v1/v2 field renames compatibility, plus
  SEP-1865 UI-visibility filtering and SEP-1686 task augmentation (`prefer_tasks=True`).
- **Collisions raise `UserError`; `tool_prefix` was the mitigation (v1 only).**
  In v1, `MCPServer(tool_prefix="weather")` renames every tool to `{prefix}_{name}` (prefix +
  trailing underscore; stripped again at call time). The docs call this out under "Using Tool
  Prefixes to Avoid Naming Conflicts." When combining toolsets with a duplicate name,
  `CombinedToolset` raises:
  > `{Toolset} defines a tool whose name conflicts with existing tool from {other}: {name!r}.`
  > `Set the `tool_prefix` attribute to avoid name conflicts.`
  ([combined.py](https://raw.githubusercontent.com/pydantic/pydantic-ai/v1.107.7/pydantic_ai_slim/pydantic_ai/toolsets/combined.py)).
  In v2, prefixing moved from a constructor arg to a wrapper: `toolset.prefixed("weather")`,
  and `load_mcp_toolsets(config_path)` automatically wraps each configured server with
  `.prefixed(server_name)` so config-file MCP servers never collide
  ([v2 mcp.py](https://raw.githubusercontent.com/pydantic/pydantic-ai/v2.55.0/pydantic_ai_slim/pydantic_ai/mcp.py)).

### Lifetime

- **Ref-counted re-entrant async context managers, entered per run by default.** From the v1
  docstring: "The first call starts the connection … Subsequent calls — from any task — share
  the same connection via reference counting. The connection is torn down when the last
  `async with` scope exits." If you don't pre-enter, `agent.run()/iter()` enters each toolset
  itself inside the run's `AsyncExitStack` — i.e. **connect per run unless you hold
  `async with agent:` open**, which keeps servers alive for the block.
- **No sync API**: `__enter__` doesn't exist on `MCPServer`/`MCPToolset` (zero matches in
  either version); `agent.run_sync()` bridges by running the async context internally.
  The v1 helper `run_mcp_servers()` is deprecated ("use `async with agent:` instead").
- The session runs in a dedicated background asyncio task so anyio cancel scopes never cross
  task boundaries. Transports: v1 `MCPServerStdio / MCPServerSSE / MCPServerStreamableHTTP / MCPServerHTTP`
  (alias of SSE, deprecated); v2 delegates transports to fastmcp
  (`StreamableHttpTransport`, `SSETransport`, `StdioTransport`, URL inference — URL is treated
  as Streamable HTTP unless the path endswith `/sse`).

### Caching / refresh

- **Cached by default, invalidated on `notifications/tools/list_changed`.** v1/v2
  `cache_tools`/`cache_resources`/`cache_prompts` all default **True**: "tools are fetched once
  and cached until either: The server sends a `notifications/tools/list_changed` notification;
  [or] the context exits. Set to `False` for servers that change tools dynamically without
  sending notifications" (v1 docstring; v2 installs a message handler that calls
  `_invalidate_tools_cache()` on `ToolListChangedNotification`). This is the one framework
  that implements *notification-driven* refresh rather than per-run refetch or a manual
  invalidation flag.
- Deferred loading for big servers: `mcp.defer_loading()` / `DeferredLoadingToolset` — "useful
  for large toolsets (e.g. MCP servers with many endpoints)"
  ([toolsets docs](https://raw.githubusercontent.com/pydantic/pydantic-ai/v1.107.7/docs/toolsets.md)).

### Guardrails

- **No output truncation/sanitization/injection mitigation in either version** — MCP results
  map through `_map_tool_result_part` (TextContent text, images → `BinaryContent`,
  `structuredContent` preferred when present) verbatim; server-authored error strings are
  returned to the model on purpose (`ModelRetry(message or 'MCP tool call failed')`; v2 makes
  this configurable as `tool_error_behavior: 'retry' | 'error' | 'failed'`). The only size
  machinery in the repo (`_ssrf.py`) is SSRF-capped URL *downloading* for multimodal input,
  not tool output.
- **HITL for MCP tools is opt-in via a toolset wrapper**: `toolset.approval_required(fn)`
  (`ApprovalRequiredToolset`) raises `ApprovalRequired` at call time; the run then ends with
  `DeferredToolRequests` as its output and resumes with
  `deferred_tool_results=DeferredToolResults(approvals={...})` — the docs explicitly name MCP
  as the target: "To require approval for calls to tools provided by a toolset (like an **MCP
  server**), see the `ApprovalRequiredToolset` documentation"
  ([deferred-tools docs](https://raw.githubusercontent.com/pydantic/pydantic-ai/v1.107.7/docs/deferred-tools.md)).
- **`tool_call_limit` does not exist in pydantic-ai** (any version) — the only symbol of that
  name is an unrelated realtime voice-session budget. Also absent: `allow_parallel_tool_calls`.
  Parallelism is governed per tool by `ToolDefinition.sequential`.
- Extras: MCP **sampling** support both directions (`allow_sampling`, `sampling_model`,
  `Agent.set_mcp_sampling_model()`; v2 `sampling_model`/`sampling_handler`), elicitation
  handler, `auth` (httpx.Auth / `"oauth"` → FastMCP OAuth / bearer string), `include_instructions=True`
  merges server initialize instructions into agent instructions as a dynamic instruction part.

### Exact current API (v2.55.0)

`MCPToolset(client: FastMCPClient | ClientTransport | FastMCP | AnyUrl | Path | str, *, id,
max_retries, tool_error_behavior='retry', process_tool_call, prefer_tasks=True,
cache_tools=True, cache_resources=True, cache_prompts=True, include_instructions=False,
include_return_schema, sampling_model, sampling_handler, elicitation_handler, log_handler,
log_level, progress_handler, message_handler, client_info, init_timeout=5, read_timeout=300,
roots, auth, verify, headers, http_client)` — full signature and the prebuilt-client conflict
rule quoted in the research transcript
([v2 mcp.py](https://raw.githubusercontent.com/pydantic/pydantic-ai/v2.55.0/pydantic_ai_slim/pydantic_ai/mcp.py)).

---

## Cross-framework comparison

| Question | LangChain / LangGraph (`langchain-mcp-adapters` → `langchain.mcp`) | OpenAI Agents SDK (py) | Claude Agent SDK (py) | LlamaIndex (`llama-index-tools-mcp`) | Pydantic AI (v1 `MCPServer` / v2 `MCPToolset`) |
|---|---|---|---|---|---|
| **1a. How tools surface** | Explicit: `list_tools` per `load_mcp_tools`/`get_tools` call, paginated ([tools.py](https://raw.githubusercontent.com/langchain-ai/langchain-mcp-adapters/main/langchain_mcp_adapters/tools.py)) | Per-run: "Every agent run calls `list_tools()` on each MCP server" ([mcp docs](https://openai.github.io/openai-agents-python/mcp/)) | Implicit: bundled CLI engine lists on connect; names `mcp__server__tool`; tool-search defers definitions on by default ([mcp docs](https://code.claude.com/docs/en/agent-sdk/mcp)) | Explicit at spec conversion: `to_tool_list_async()` → `list_tools()` ([base.py](https://github.com/run-llama/llama_index/blob/main/llama-index-integrations/tools/llama-index-tools-mcp/llama_index/tools/mcp/base.py)) | Per-run lazy discovery: toolset `get_tools(ctx)` inside `agent.run()`; no connect-time registration ([v1 mcp.py](https://raw.githubusercontent.com/pydantic/pydantic-ai/v1.107.7/pydantic_ai_slim/pydantic_ai/mcp.py)) |
| **1b. JSON-Schema mapping** | Pass-through: `args_schema=tool.inputSchema` dict, annotations/`_meta` → metadata | Normalized: adds `properties: {}` if missing; optional `convert_schemas_to_strict` (add `additionalProperties: False`, `required` all, `oneOf`→`anyOf`, best-effort) | None by SDK (CLI-side); schemas go to Claude Code as-is | JSON-Schema → pydantic model (`create_model_from_json_schema`: `enum`→`Literal`, `$ref`→nested models, required/defaults) | Pass-through: `parameters_json_schema=inputSchema` (+ v2 `outputSchema`→`return_schema`, SEP-1686/SEP-1865 handling) |
| **1c. Name collisions** | Default: **silent collision** (raw names). Opt-in `tool_name_prefix=True` → ` "{server}_{tool}"`; call still uses native name | **Hard `UserError`** listing dupes; opt-in `mcp_config={'include_server_in_tool_names': True}` → `mcp_{server}__{tool}`, 64-char cap + SHA-1 hash suffix, reserved-name protection | **Namespaced by construction** (`mcp__<server>__<tool>`, always); cross-server post-namespace behavior undocumented; scope precedence, reserved names rejected | **Silent last-wins dict in core** (`tools_by_name[...]`), no warning, no prefix API in any release | **Hard `UserError`** with per-toolset hint ("Set the `tool_prefix`…"); v1 `tool_prefix` param, v2 wrapper `toolset.prefixed(name)` (auto-applied by `load_mcp_toolsets`) |
| **2a. Connection lifetime** | **Stateless per-call** by default (new session + initialize per tool call); explicit pin via `client.session(name)`; context-manager use removed in 0.1.0 | **Long-lived user-managed sessions**: `connect()` before use, `cleanup()` after; sessions shared across agents/runs; `MCPServerManager` bulk-lifecycle, reconnect/backoff | **CLI process owns them**: `query()` = fresh process/connections per call; `ClaudeSDKClient` = persistent session; `reconnect_mcp_server`/`toggle_mcp_server` streaming-only | **New session + `initialize()` per API call** (incl. per `tools/list`), no reuse option; only httpx client reused | **Ref-counted re-entrant CM**: connect per run unless held open via `async with agent:`; torn down when last scope exits |
| **2b. Sync bridging** | None (async-only tools; sync inv. raises) | None (async-native SDK) | None (subprocess/CLI, sync-able from caller's side only) | `to_tool_list()` runs its own `asyncio.run` (errors inside a loop); tools are async | `agent.run_sync()` internally enters the async context; CM itself async-only |
| **3. Tool-list cache / refresh** | None in adapter (re-list per load); successor namespace: TTL-flag cache w/ `use`/`refresh`/`bypass` modes | `cache_tools_list=False` default (fetch per run/list); manual `invalidate_tools_cache()`; generation-guarded, deep-copied snapshots | CLI-side: discovery cache (`MCP_DISCOVERY_CACHE=1`), `list_changed` → refresh only tool list, keep-on-failure; SDK surface = `get_mcp_status` etc. | **None** — `tools/list` refetched (fresh session) on every `to_tool_list_async`; only `$defs` model classes cached | **Default-on cache**, invalidated by `notifications/tools/list_changed` or context exit; `cache_tools=False` for dynamic servers; deferred loading for big lists |
| **4a. Output guardrails** | None (blocks verbatim; audio unsupported); error → model-visible `ToolMessage(status="error")` | None by default; opt-in `tool_output_trimmer`; generic error function hides exception text | **Hard limits**: >25k tokens → persisted to file + error mention; warning >10k tokens; >50k chars persisted (unless `_meta anthropic/maxResultSizeChars` ≤500k); error text truncated ~11k → 5k+5k | None (`str(CallToolResult)` fallback; exceptions → `is_error` ToolOutput) | None; server error strings returned to model by design (`ModelRetry`, or v2 `tool_error_behavior`), verbatim |
| **4b. HITL / approval for MCP tools** | Interceptor protocol; successor: `HumanInTheLoopMiddleware` + `InterruptOnConfig`; elicitation → `interrupt()` **on by default** | `require_approval="always"/"never"/per-tool/callable` (callable fail-closed); standard HITL interrupt, survives pause/resume; optional server-wide input/output guardrails | Permission-first: `allowed_tools` globs, `disallowed_tools`, `can_use_tool` (only fires on "ask" rules), PreToolUse hooks; connectors `ask`/`blocked` | None MCP-specific; DIY via workflow `InputRequiredEvent` | Opt-in `toolset.approval_required(...)` → `DeferredToolRequests` output + `DeferredToolResults` resume |
| **Loop limits near MCP** | None in adapter; `ToolCallLimitMiddleware` (LangChain v1) or `recursion_limit` (LangGraph) | `max_turns` (`DEFAULT_MAX_TURNS = 10`, `MaxTurnsExceeded`) — no MCP-specific limit | CLI engine (no exposed per-run tool-call cap in py SDK); tool-search catalog cap 10k | Agent-level `max_iterations` (default 20) | **No `tool_call_limit` exists**; `ToolDefinition.sequential` per tool |

---

## Spec-relevant takeaways for AgentGraphStudio

Given the backend shapes — tools run in the Docker sandbox per worker run, DSPy tool
descriptors come from host-side metadata (`backend/src/canvas_server/tool_factory.py`), and
execution happens in the BackgroundRunWorker process:

1. **Collision policy must be explicit, not incidental.** The mainstream split is
   `UserError` (OpenAI, Pydantic AI) vs silent-last-wins (LlamaIndex) vs prefix-to-disambiguate
   (Claude SDK always, OpenAI/LangChain/Pydantic AI opt-in). For a canvas builder where users
   wire multiple MCP servers into one agent, following OpenAI's shape — **error with the
   offending names + hint to enable server-prefixed naming** — is the most defensible, and
   prefixing should be per-server config (`tool_prefix` in Pydantic AI v1 is exactly the
   ergonomic shape to copy; it strips the prefix again at call time so the MCP invocation is
   unprefixed).
2. **Session lifetime should follow OpenAI's user-managed-session shape rather than
   per-call sessions.** Per-call session+initialize (langchain-mcp-adapters default, all of
   LlamaIndex) is simple but pays initialize + handshake per tool call and never reuses a
   server session; OpenAI's `connect()`/`cleanup()` with an `MCPServerManager`-style registry
   of `active_servers`/`failed_servers` maps cleanly to the existing BackgroundRunWorker
   claiming a run and to the warm-pool precedent of `SandboxManager`. Re-initialize on HTTP 404
   (spec-mandated session end) is the required reconnect primitive either way.
3. **Tool-list caching**: pick Pydantic AI's pattern — **cache by default, invalidate on
   `notifications/tools/list_changed`** (and on teardown), over OpenAI's default-refetch — for
   canvas runs that span many turns; a per-run `cache_tools=False` escape hatch covers
   servers that don't honor `listChanged`. Note OpenAI's cache deep-copies results so callers
   can't mutate the shared cache.
4. **Guardrails are not free everywhere — pick deliberately.** Default posture across
   frameworks is "tool output goes to the model verbatim"; only Claude Agent SDK ships hard
   output limits (25k tokens persisted-to-file, 50k-char cap). Given AgentGraphStudio already
   treats tool failures as call-time-raised model observations (StreamingReAct error stubs),
   the analogous MCP behavior is `isError`-aware text propagation plus a configurable output
   cap, and MCP-tool approval wired into the existing HITL/approval event plumbing rather than
   a new mechanism.
5. **Everything MCP is async.** All five frameworks are async-native at this layer; the
   BackgroundRunWorker's async runtime is the right place to own MCP sessions (never a
   thread-blocked sync wrapper), which also matches how `tool_factory` already isolates
   execution from the host.

---

## Sources

- MCP spec (2025-06-18): [transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports) · [tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) · [security best practices](https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices)
- LangChain/LangGraph: [langchain-mcp-adapters README](https://github.com/langchain-ai/langchain-mcp-adapters) · [tools.py](https://raw.githubusercontent.com/langchain-ai/langchain-mcp-adapters/main/langchain_mcp_adapters/tools.py) · [client.py](https://raw.githubusercontent.com/langchain-ai/langchain-mcp-adapters/main/langchain_mcp_adapters/client.py) · [sessions.py](https://raw.githubusercontent.com/langchain-ai/langchain-mcp-adapters/main/langchain_mcp_adapters/sessions.py) · [interceptors.py](https://raw.githubusercontent.com/langchain-ai/langchain-mcp-adapters/main/langchain_mcp_adapters/interceptors.py) · [structured.py (langchain-core)](https://raw.githubusercontent.com/langchain-ai/langchain/master/libs/core/langchain_core/tools/structured.py) · [tool-node.py (LangGraph)](https://raw.githubusercontent.com/langchain-ai/langgraph/main/libs/prebuilt/langgraph/prebuilt/tool_node.py) · [mcp tools docs](https://docs.langchain.com/oss/python/langchain/mcp/tools) · [mcp connections docs](https://docs.langchain.com/oss/python/langchain/mcp/connections) · [mcp auth docs](https://docs.langchain.com/oss/python/langchain/mcp/auth) · [migration guide](https://docs.langchain.com/oss/python/migrate/langchain-mcp-adapters) · [ToolCallLimitMiddleware reference](https://reference.langchain.com/python/langchain/agents/middleware/tool_call_limit/ToolCallLimitMiddleware)
- OpenAI Agents SDK: [mcp docs](https://openai.github.io/openai-agents-python/mcp/) · [agent.py](https://github.com/openai/openai-agents-python/blob/main/src/agents/agent.py) · [mcp/server.py](https://github.com/openai/openai-agents-python/blob/main/src/agents/mcp/server.py) · [mcp/util.py](https://github.com/openai/openai-agents-python/blob/main/src/agents/mcp/util.py) · [mcp/manager.py](https://github.com/openai/openai-agents-python/blob/main/src/agents/mcp/manager.py) · [strict_schema.py](https://github.com/openai/openai-agents-python/blob/main/src/agents/strict_schema.py) · [tool_output_trimmer.py](https://github.com/openai/openai-agents-python/blob/main/src/agents/extensions/tool_output_trimmer.py)
- Claude Agent SDK (py): [types.py](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/types.py) · [subprocess_cli.py](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/transport/subprocess_cli.py) · [sdk_mcp_bridge.py](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/sdk_mcp_bridge.py) · [client.py](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/client.py) · [Agent SDK MCP docs](https://code.claude.com/docs/en/agent-sdk/mcp) · [Agent SDK python reference](https://code.claude.com/docs/en/agent-sdk/python) · [Agent SDK custom tools](https://code.claude.com/docs/en/agent-sdk/custom-tools) · [Claude Code MCP reference](https://code.claude.com/docs/en/mcp) · [permissions](https://code.claude.com/docs/en/permissions) · [security](https://code.claude.com/docs/en/security)
- LlamaIndex: [tools/mcp base.py](https://github.com/run-llama/llama_index/blob/main/llama-index-integrations/tools/llama-index-tools-mcp/llama_index/tools/mcp/base.py) · [client.py](https://github.com/run-llama/llama_index/blob/main/llama-index-integrations/tools/llama-index-tools-mcp/llama_index/tools/mcp/client.py) · [tool_spec_mixins.py](https://github.com/run-llama/llama_index/blob/main/llama-index-integrations/tools/llama-index-tools-mcp/llama_index/tools/mcp/tool_spec_mixins.py) · [package README](https://github.com/run-llama/llama_index/blob/main/llama-index-integrations/tools/llama-index-tools-mcp/README.md) · [MCP module guide](https://developers.llamaindex.ai/python/framework/module_guides/mcp/llamaindex_mcp/) · [core tools/calling.py](https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/tools/calling.py) · [agent base_agent.py](https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/agent/workflow/base_agent.py)
- Pydantic AI: [v1.107.7 mcp.py](https://raw.githubusercontent.com/pydantic/pydantic-ai/v1.107.7/pydantic_ai_slim/pydantic_ai/mcp.py) · [v2.55.0 mcp.py](https://raw.githubusercontent.com/pydantic/pydantic-ai/v2.55.0/pydantic_ai_slim/pydantic_ai/mcp.py) · [v1 toolsets/prefixed.py](https://raw.githubusercontent.com/pydantic/pydantic-ai/v1.107.7/pydantic_ai_slim/pydantic_ai/toolsets/prefixed.py) · [v1 toolsets/combined.py](https://raw.githubusercontent.com/pydantic/pydantic-ai/v1.107.7/pydantic_ai_slim/pydantic_ai/toolsets/combined.py) · [v1 toolsets/approval_required.py](https://raw.githubusercontent.com/pydantic/pydantic-ai/v1.107.7/pydantic_ai_slim/pydantic_ai/toolsets/approval_required.py) · [v1 docs mcp/client.md](https://raw.githubusercontent.com/pydantic/pydantic-ai/v1.107.7/docs/mcp/client.md) · [v1 docs toolsets.md](https://raw.githubusercontent.com/pydantic/pydantic-ai/v1.107.7/docs/toolsets.md) · [v1 docs deferred-tools.md](https://raw.githubusercontent.com/pydantic/pydantic-ai/v1.107.7/docs/deferred-tools.md) · [current MCP overview](https://pydantic.dev/docs/ai/mcp/overview/) · [PyPI pydantic-ai](https://pypi.org/pypi/pydantic-ai/json)