# MCP Streamable HTTP Transport + Python Client SDK Facts

**Research ticket:** [#118](https://github.com/manojmanivannan/AgentGraphStudio/issues/118)
**Date:** 2026-10-10
**Scope:** Current, factual state of the MCP Streamable HTTP transport (spec versions 2025-03-26 → 2026-07-28) and the Python client SDKs (`mcp` official SDK v2/v1, FastMCP v4), plus what a per-run connection actually costs. Feeds decision tickets #119–#121 (connection lifetime, tool-descriptor conversion, execution-engine integration).

All claims are sourced from primary sources — the spec at [modelcontextprotocol.io](https://modelcontextprotocol.io), the [`modelcontextprotocol/python-sdk`](https://github.com/modelcontextprotocol/python-sdk) and [`PrefectHQ/fastmcp`](https://github.com/PrefectHQ/fastmcp) source trees (fetched from GitHub raw at `main` and current tags), and PyPI — read on **2026-10-10**. Version-dependent facts are flagged inline.

---

## TL;DR

| Question | Answer |
|---|---|
| Latest spec revision | **2026-07-28** — and it is a **breaking** revision for HTTP clients: it removes protocol-level sessions (`Mcp-Session-Id`), the HTTP `GET` stream endpoint, `initialize`/`notifications/initialized` handshake, and `Last-Event-ID` resumability. The "classic" shape (single endpoint, POST+GET, session header) spans 2025-03-26 → 2025-11-25 and is what current SDKs still speak by default. |
| Auth model | **Authorization is OPTIONAL** in every revision. When a server requires auth, the spec describes OAuth 2.1 (RS/AS split, Protected Resource Metadata RFC 9728, RFC 8707 resource indicators; DCR deprecated 2026-07-28 in favor of Client ID Metadata Documents). A plain header/API-key scheme is never specified but also never forbidden — it lives outside the OAuth normative scope. |
| Tool list shape | `tools/list` → `Tool {name, title?, description, inputSchema, outputSchema?, annotations?, _meta?}`. `inputSchema` is a raw JSON Schema object with `type: "object"` at the root (2026-07-28 loosens it to any JSON Schema 2020-12 keywords). Tool execution errors are returned **in-band** as `isError: true` results; only protocol-level errors (unknown tool, bad params) are JSON-RPC errors. |
| Official SDK | **`mcp` 2.3.0** (PyPI, 2026-10-02) is a **full client rewrite** (`Client`, `streamable_http_client`, `MCPError`, `httpx2`; 2-tuple streams, floats not `timedelta`s; no public session-id accessor). The familiar `streamablehttp_client(headers=..., auth=..., timeout=...)` with the 3-tuple yield is the **deprecated 1.x wrapper** (`@deprecated("Use streamable_http_client instead.")`); the v1.x line ended at 1.30.0 and gets only critical fixes. |
| FastMCP | **`fastmcp` 4.1.0** (2026-10-08, repo moved to `PrefectHQ/fastmcp`) is built on the official SDK v2 and layers: URL-string transport inference, result auto-parsing (`CallToolResult.data` hydrated from `outputSchema`, `{"result": …}` unwrapping), `ToolError` raised by default, `BearerAuth(token)` / `auth="oauth"` batteries, auto-pagination + response caching, and protocol-era negotiation (`mode="auto"`). |
| Per-run connection | Cheap: **zero handshake cost** under the 2026-07-28 stateless protocol (every request self-describes); under the classic protocol, 2 HTTP round trips (`initialize` + `initialized` notification) plus an optional GET SSE stream — all reused across calls within one transport context. HTTP-layer defaults everywhere: connect/write/pool **30 s**, read **300 s**. Server restart / session expiry mid-run surfaces as a **404 → `MCPError("Session terminated")`** with **no auto-reinitialize in any SDK** — recovery is rebuild-the-transport, which makes per-run connection lifetime the pragmatic default. |

---

## 0. Snapshot: versions in play (verified 2026-10-10)

| Component | Current | Notes |
|---|---|---|
| MCP spec | **2026-07-28** | Previous revisions: 2025-11-25, 2025-06-18, 2025-03-26, 2024-11-05. A `draft` line exists in-repo for upcoming changes. ([llms.txt](https://modelcontextprotocol.io/llms.txt), [changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog)) |
| `mcp` (official SDK) | **2.3.0**, 2026-10-02 | Python ≥ 3.10 (classifiers 3.10–3.14). v1.x line ended at **1.30.0** ([VERSIONING.md](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/VERSIONING.md): two-line support — "2.x (`main`) — bug fixes, security fixes, and features. 1.x (`v1.x` branch) — critical bug fixes and security fixes.") |
| `fastmcp` | **4.1.0**, 2026-10-08 | Python ≥ 3.10. Repo `PrefectHQ/fastmcp` (source lives under `fastmcp_slim/`). Depends on `mcp>=2.0.0,<3`, `mcp-types>=2.0.0,<3`, `httpx2>=2.5.0` ([pyproject.toml](https://raw.githubusercontent.com/PrefectHQ/fastmcp/main/fastmcp_slim/pyproject.toml)) |
| `httpx2` | 2.13.1 | Pydantic-picked-up **continuation of httpx** under a new name ("With HTTPX itself seeing limited activity recently, Pydantic is picking up stewardship under the HTTPX2 name") — same API, BSD-3. ([pypi.org/project/httpx2](https://pypi.org/project/httpx2/)) |

**AgentGraphStudio compat note:** backend pins `requires-python = ">=3.12"` — above both SDKs' floor. Neither HTTP/MCP client is a dependency today (`backend/pyproject.toml`).

---

## 1. Spec: Streamable HTTP — the "classic" shape (2025-03-26 → 2025-11-25)

Sources: [2025-06-18 transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports), [2025-11-25 transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), [2025-03-26 transports](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports).

### 1.1 Single endpoint

- **"The server MUST provide a single HTTP endpoint path (hereafter referred to as the MCP endpoint) that supports both POST and GET methods."** Example in spec: `https://example.com/mcp`. The path itself is not mandated — `/mcp` is only an example.
- Security (all revisions): servers **MUST** validate the `Origin` header (DNS-rebinding protection); 403 Forbidden on present-and-invalid `Origin` (formalized starting 2025-11-25); **SHOULD** bind localhost when local; **SHOULD** "implement proper authentication for all connections."

### 1.2 POST semantics

1. Client **MUST** use HTTP POST for every JSON-RPC message; body **MUST** be a single JSON-RPC request, notification, or response.
   - *Version drift:* [2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) also allowed JSON-RPC **batching** (array bodies); [2025-06-18 removed it](https://modelcontextprotocol.io/specification/2025-06-18/changelog) ("Remove support for JSON-RPC batching", PR #416).
2. Client **MUST** include `Accept: application/json, text/event-stream` on every POST.
3. For a request, the server **MUST** return either `application/json` (single JSON object) **or** `text/event-stream` (SSE stream); the client **MUST** support both. The response SSE stream **SHOULD** carry request-scoped notifications then the response, and the server **SHOULD** close the stream after the response ("unless the session expires").
4. For a notification or response, the server **MUST** return **202 Accepted** with no body (MUST NOT wait), or an HTTP error status (e.g. 400); the error body **MAY** be a JSON-RPC error response with no `id`.

### 1.3 GET semantics (removed in 2026-07-28 — see §2)

- The client **MAY** issue a GET to open a standalone SSE stream for server-initiated messages; **MUST** send `Accept: text/event-stream`.
- The server **MUST** return `text/event-stream` **or 405 Method Not Allowed** if it offers no such stream.
- On that stream the server **MUST NOT** send JSON-RPC *responses* unless resuming a previous client request; the client **MAY** keep multiple SSE streams open simultaneously, but the server **MUST NOT** broadcast the same message on multiple streams (each message is delivered on exactly one stream).

### 1.4 Session management (`Mcp-Session-Id`)

Verbatim ([2025-06-18 §Session Management](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#session-management)):

1. A server **MAY** assign a session ID at initialization time via the `Mcp-Session-Id` header on the `InitializeResult` response. It **SHOULD** be globally unique and cryptographically secure, and **MUST** contain only visible ASCII (0x21–0x7E).
2. If returned, clients **MUST** echo it in the `Mcp-Session-Id` header on **all subsequent HTTP requests**. Servers requiring it **SHOULD** return **400 Bad Request** when it is missing (other than on initialize).
3. The server **MAY** terminate the session at any time; after that it **MUST** respond to requests with that session ID with **404 Not Found**.
4. On receiving **404** for a session-bearing request, the client **MUST** **start a new session** with a fresh `InitializeRequest` (no session ID).
5. Clients **SHOULD** explicitly terminate with **HTTP DELETE** to the MCP endpoint; the server **MAY** reject with **405** (not allowing client-initiated termination).

No expiry TTL is specified; protocol version header `MCP-Protocol-Version: <version>` became MUST-on-every-request in 2025-06-18 ("If using HTTP, the client **MUST** include the `MCP-Protocol-Version: <protocol-version>` HTTP header on all subsequent requests"; absent header → server SHOULD assume `2025-03-26`; unsupported version → 400 Bad Request).
*Spelling drift:* 2025-11-25 renames the header to `MCP-Session-Id` and adds "The client **MUST** handle the session ID in a secure manner" (session-hijacking mitigations). Headers are case-insensitive per HTTP.

### 1.5 SSE resumability (`Last-Event-ID`) — removed in 2026-07-28

- Servers **MAY** attach SSE event `id`s (globally unique per session, per-stream cursors); the client **SHOULD** resume a broken stream with a GET carrying `Last-Event-ID`; the server **MAY** replay the missing messages of *that stream only* ("The server **MUST NOT** replay messages that would have been delivered on a different stream").
- [2025-11-25 (SEP-1699)](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) adds **SSE polling**: the server **SHOULD** immediately send an empty-data event to prime reconnection, **MAY** close the connection while keeping the stream logically open, **SHOULD** send an SSE `retry` field first, and the client **MUST** respect `retry` before reconnecting ("The client **SHOULD** then 'poll' the SSE stream by attempting to reconnect"; resumption is always via GET + `Last-Event-ID`, regardless of how the stream originated).

### 1.6 Other protocol-level changes affecting HTTP clients

- JSON-RPC batching: allowed in 2025-03-26, **removed** in 2025-06-18.
- **HTTP+SSE transport (2024-11-05)** was **replaced** by Streamable HTTP in 2025-03-26 ("This replaces the HTTP+SSE transport from protocol version 2024-11-05") and informally described as deprecated thereafter. In **2026-07-28** it is formally **reclassified as Deprecated** under the new feature-lifecycle policy (SEP-2596), "eligible for removal in a future revision", with a minimum twelve-month deprecation window. Backward-compat probe (all revisions): POST an `initialize`; on 400/404/405 fall back to GET-for-`endpoint`-event (legacy detection); 2026-07-28 refines this — only fall back when the error body is *not* a recognized modern JSON-RPC error.

---

## 2. Spec: the 2026-07-28 revision — stateless Streamable HTTP

Sources: [2026-07-28 Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http.md), [2026-07-28 changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog).

The binding page warns verbatim:

> "Revision 2026-07-28 changed the behavior of Streamable HTTP. Clients must ensure they handle backwards compatibility correctly. Changes included:
> * Removal of the GET stream endpoint.
> * Removal of protocol-level sessions."

Full inventory:

1. **`initialize` handshake removed — MCP is stateless.** "Make MCP stateless: remove the `initialize`/`notifications/initialized` handshake. Every request now carries its protocol version and client capabilities in `_meta` (`io.modelcontextprotocol/protocolVersion`, `io.modelcontextprotocol/clientCapabilities`)… Version mismatches return `UnsupportedProtocolVersionError`" (SEP-2575). Clients SHOULD identify themselves per request (`io.modelcontextprotocol/clientInfo`).
2. **Protocol-level sessions removed** (SEP-2567): "Remove protocol-level sessions and the `Mcp-Session-Id` header from the Streamable HTTP transport. List endpoints (`tools/list`, …) no longer vary per-connection. Servers that need cross-call state use explicit, server-minted handles passed as ordinary tool arguments." **No `Mcp-Session-Id`, no DELETE termination.**
3. **New discovery RPC `server/discover`**: servers **MUST** implement it (advertises supported protocol versions, capabilities, identity); clients **MAY** probe it first, or use it as the STDIO backward-compat probe.
4. **GET endpoint removed**; long-lived notifications come from **`subscriptions/listen`** — a single long-lived POST-response SSE stream for opted-in change notifications (`toolsListChanged`, `promptsListChanged`, `resourcesListChanged`, `resourceSubscriptions`). Request-scoped notifications (`notifications/progress`, `notifications/message`) still flow on the originating request's own response stream. There is deliberately **no client-to-server notification over Streamable HTTP** in this revision ("The only client-sent notification in the core protocol, `notifications/cancelled`, is used only on the stdio transport; on Streamable HTTP, closing the SSE response stream is itself the cancellation signal").
5. **Resumability removed**: "Remove SSE stream resumability and message redelivery (the `Last-Event-ID` header and SSE event IDs)… A broken response stream loses the in-flight request; clients **MUST** re-issue it as a new request with a new request ID." Binding page: "Resumable SSE streams via `Last-Event-ID` are not supported."
6. **Cancellation is now transport-level**: "Closing the SSE response stream **MUST** be treated by the server as cancellation of that request."
7. **Server-initiated JSON-RPC requests removed.** "The server **MUST NOT** send independent JSON-RPC *requests* on this stream. Server-to-client interactions (sampling, elicitation, list-roots) are embedded as input requests inside an `InputRequiredResult` per MRTR (SEP-2322)" — the client retries the original request with `inputResponses`. All results carry a required `resultType` (`"complete"` | `"input_required"`); earlier-protocol results missing it are treated as `"complete"`.
8. **New required request headers** (SEP-2243 HTTP header standardization): every POST **MUST** include
   - `MCP-Protocol-Version` (MUST match the `_meta` protocolVersion; mismatch → **400** + error code `-32020` `HeaderMismatch`),
   - `Mcp-Method` (the JSON-RPC `method`), and `Mcp-Name` (`params.name` / `params.uri` for `tools/call`, `resources/read`, `prompts/get`) — both **REQUIRED**;
   - additionally `Mcp-Param-{Name}` mirrored headers: servers **MAY** annotate tool inputSchema properties with `x-mcp-header` (primitives only, `properties`-reachable paths only), and conforming clients **MUST** mirror those values into headers with base64-sentinel encoding (`=?base64?…?=`) for non-ASCII values.
   - Unknown method: server **MUST** return **404** with JSON-RPC error `-32601`.
9. **Proxy hints:** servers **SHOULD** send `X-Accel-Buffering: no` on SSE streams and are "encouraged to periodically emit an SSE comment line… (`:\r\n`) as a keep-alive" on long-lived `subscriptions/listen` streams so intermediaries/idle timeouts don't kill quiet streams. (No keepalive is specified for ordinary request-scoped streams; these SHOULD terminate with the response.)
10. **List-response caching** (SEP-2549): `tools/list` etc. now return `ttlMs` (freshness hint, ms) and `cacheScope` ("public" | "private") via a new `CacheableResult` interface; servers SHOULD return tools in deterministic order (prompt-cache friendliness).
11. **Schema looseness** (SEP-2106): `inputSchema` / `outputSchema` may use any JSON Schema 2020-12 keyword; `structuredContent` may be any JSON value.
12. **Legacy-compat rules for modern servers:** GET/DELETE from old clients → **405**; `Mcp-Session-Id` header → ignore (do not mint/echo); `Last-Event-ID` → ignore.
13. `ping`, `logging/setLevel`, `notifications/roots/list_changed` removed (log level now per-request via `io.modelcontextprotocol/logLevel` in `_meta`); Roots/Sampling/Logging features as a whole are **deprecated** (SEP-2577); experimental tasks moved to the `io.modelcontextprotocol/tasks` **extension**.

**Status-code ledger** (normative occurrences; 406/415 appear **nowhere** in the spec repo — those are SDK implementation choices, not spec semantics):

| Status | Classic (2025-03-26 → 2025-11-25) | 2026-07-28 |
|---|---|---|
| 200/202 | 202 for notification/response POSTs | 202 for notification POSTs (core protocol defines no HTTP notifications in practice) |
| 400 | reject non-assignable input (e.g. 400); missing session ID when required (SHOULD); invalid/unsupported `MCP-Protocol-Version` | `HeaderMismatch` (-32020), `UnsupportedProtocolVersionError`, missing capabilities, header validation |
| 403 | invalid `Origin` (2025-11-25+); auth insufficient scope | invalid `Origin`; auth insufficient scope (403 + `WWW-Authenticate: Bearer error="insufficient_scope"`, scope="…") |
| 404 | expired/terminated session (MUST) → client MUST re-initialize | unknown RPC method (MUST, with `-32601`) |
| 405 | GET without SSE support; DELETE-refusal | GET/DELETE from legacy clients (SHOULD) |

---

## 3. Spec: tool listing & calling — the JSON-schema shapes

Source: [2025-06-18 server/tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools.md), plus 2026-07-28 deltas above.

- `tools/list` returns `{tools: [...], nextCursor?}` with [pagination](https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/pagination). `Tool` fields: `name` (unique per server — the spec imposes no cross-server uniqueness convention), `title` (optional display name), `description`, `inputSchema` (JSON Schema declaring expected parameters), `outputSchema` (optional), `annotations` (optional hints), plus 2.x-era `_meta`, `execution`, `icons`.
- `inputSchema` is a **raw JSON Schema object with `type: "object"` at the root** in the SDK types — the type model literally restricts `type: Literal["object"]` with `extra="allow"`, so arbitrary JSON Schema keywords pass through (loosened further in 2026-07-28 / SEP-2106 to any 2020-12 keyword). Example from the spec:

```json
{
  "name": "get_weather",
  "title": "Weather Information Provider",
  "description": "Get current weather information for a location",
  "inputSchema": {
    "type": "object",
    "properties": { "location": { "type": "string", "description": "City name or zip code" } },
    "required": ["location"]
  }
}
```

- `outputSchema` is the mirror for structured output: when present, "Servers **MUST** provide structured results that conform to this schema" and "Clients **SHOULD** validate structured results against this schema." `CallToolResult` therefore carries:
  - `content: []` — unstructured blocks: `text` (`{type, text}`), `image`, `audio`, `resource_link`, `resource` (embedded); content blocks support optional `annotations` (`audience`, `priority`).
  - `structuredContent: {}` — JSON-object result; "a tool that returns structured content **SHOULD** also return the serialized JSON in a TextContent block."
  - `isError` (bool).
- **Two error channels** (verbatim): "Any errors that originate from the tool **SHOULD** be reported inside the result object, with `isError` set to true, *not* as an MCP protocol-level error response… any errors in *finding* the tool… should be reported as an MCP error response." Unknown tool → JSON-RPC `-32602` ("Unknown tool: …"). Execution failure → normal result, `isError: true`, message in `content[0].text`.
- Trust posture: tool **annotations** ("MUST be considered untrusted unless they come from trusted servers"); clients **SHOULD** "validate tool results before passing to LLM", implement timeouts for tool calls, and keep a human in the loop able to deny invocations.
- 2026-07-28 additions on top: `ttlMs`/`cacheScope` on list responses, deterministic tool ordering SHOULD, `x-mcp-header` mirroring for `tools/call`, and `Mcp-Name: <tool>` header mirroring.

---

## 4. Spec: the current auth model

Sources: [2025-03-26 authorization](https://modelcontextprotocol.io/specification/2025-03-26/basic/authorization), [2025-06-18 authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization), [2026-07-28 authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/index.md), [2025-11-25 changelog](https://modelcontextprotocol.io/specification/2025-11-25/changelog).

### 4.1 Authorization is OPTIONAL — in every revision

Word-for-word identical in 2025-03-26, 2025-06-18, and 2026-07-28:

> "Authorization is **OPTIONAL** for MCP implementations. When supported:
> * Implementations using an HTTP-based transport **SHOULD** conform to this specification.
> * Implementations using an STDIO transport **SHOULD NOT** follow this specification, and instead retrieve credentials from the environment.
> * Implementations using alternative transports **MUST** follow established security best practices for their protocol."

Consequences: OAuth 2.1 is mandatory *within* the authorization spec ("Authorization servers **MUST** implement OAuth 2.1"), but a server that uses no auth, or a custom `Authorization` / API-key header scheme, is simply outside the OAuth framework's normative scope — the spec nowhere forbids or endorses API-key auth; the only transport-level normative language is the security warning "Servers **SHOULD** implement proper authentication for all connections." When OAuth *is* in play, `Authorization: Bearer <access-token>` is required on every HTTP request and "Access tokens **MUST NOT** be included in the URI query string"; error table fixed across revisions: **401** (unauthorized/invalid/expired), **403** (invalid/insufficient scopes), **400** (malformed request).

### 4.2 Evolution

- **2025-03-26:** single-model OAuth 2.1 for public clients with PKCE (REQUIRED for all clients); RFC 8414 metadata discovery (fallback default `/authorize` `/token` `/register` paths under the server base URL); RFC 7591 Dynamic Client Registration SHOULD.
- **2025-06-18** (the big restructure): "Classify MCP servers as OAuth Resource Servers, adding protected resource metadata to discover the corresponding Authorization server" — MCP server = resource server, client = OAuth 2.1 client, AS may be separate. **MUSTs introduced:** servers implement Protected Resource Metadata (RFC 9728); clients use it for AS discovery; servers use `WWW-Authenticate` on 401 pointing at the resource-metadata URL; tokens bound to audience (RFC 8707 `resource` parameter MUST in auth+token requests, canonical server URI, "MCP servers **MUST** validate that access tokens were issued specifically for them"; "MCP servers **MUST NOT** accept or transit any other tokens").
- **2025-11-25:** `WWW-Authenticate` relaxed to **optional** with `.well-known` fallback (SEP-985); OIDC Discovery 1.0 allowed for AS metadata (PR #797); incremental consent via `WWW-Authenticate` scope challenges (SEP-835); **Client ID Metadata Documents** introduced as recommended client registration (SEP-991); invalid `Origin` → 403.
- **2026-07-28:** registration inverted — "Authorization servers and MCP clients **SHOULD** support OAuth Client ID Metadata Documents"; "Authorization servers and MCP clients **MAY** support… RFC7591. Note that Dynamic Client Registration is deprecated" (retained for compat). RFC 9207 `iss` validation added (clients **MUST** validate a present `iss` against the recorded issuer before redeeming codes). Step-up scope flow formalized (403 + `WWW-Authenticate: Bearer error="insufficient_scope", scope="…"`; clients accumulate scopes). PRM (RFC 9728) and RFC 8707/8414+OIDC MUSTs intact. Optional auth **extensions** (e.g. client credentials) live outside the core spec at [github.com/modelcontextprotocol/ext-auth](https://github.com/modelcontextprotocol/ext-auth).

**Practical upshot for a client:** you must handle three server postures — (a) no auth, (b) a static token/API-key style scheme (just a header; the server is simply not using the spec's OAuth model), (c) OAuth 2.1 with the 401→PRM→AS-discovery flow.

### 4.3 401 challenge example (2026-07-28)

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer resource_metadata="https://mcp.example.com/.well-known/oauth-protected-resource",
                  scope="files:read"
```

---

## 5. Official Python SDK — `mcp` 2.x (current) vs 1.x (legacy)

Primary sources: [`mcp/client/streamable_http.py`](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/src/mcp/client/streamable_http.py), [`mcp/client/session.py`](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/src/mcp/client/session.py), [`mcp/client/client.py`](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/src/mcp/client/client.py), [`mcp/shared/exceptions.py`](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/src/mcp/shared/exceptions.py), [`examples/snippets/clients/streamable_basic.py`](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/examples/snippets/clients/streamable_basic.py) at `main` (2.3.0) and tag [`v1.30.0`](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/v1.30.0/src/mcp/client/streamable_http.py).

### 5.1 The 2.x rewrite (what you get on `uv add mcp` today)

Transport — signature at `main` (2.3.0), verbatim:

```python
@asynccontextmanager
async def streamable_http_client(
    url: str,
    *,
    http_client: httpx2.AsyncClient | None = None,
    terminate_on_close: bool = True,
    max_sse_event_size: int | None = DEFAULT_MAX_SSE_EVENT_SIZE,   # 1 MiB
) -> AsyncGenerator[TransportStreams, None]:
```

- **No `headers` / `auth` / `timeout` / `sse_read_timeout` parameters.** Docstring: *"`http_client`: Optional pre-configured httpx2.AsyncClient. If None, a default client with recommended MCP timeouts will be created. **To configure headers, authentication, or other HTTP settings, create an httpx2.AsyncClient and pass it here.**"* Header/API-key auth is therefore done at the httpx2 client level.
- Default HTTP behavior lives in [`shared/_httpx_utils.py`](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/src/mcp/shared/_httpx_utils.py): `MCP_DEFAULT_TIMEOUT = 30.0`, `MCP_DEFAULT_SSE_READ_TIMEOUT = 300.0` → `httpx2.Timeout(30.0, read=300.0)` (connect/write/pool 30 s; read 300 s — the read phase covers streaming responses).
- **Yield is a 2-tuple** `TransportStreams = tuple[ReadStream[SessionMessage | Exception], WriteStream[SessionMessage]]` ([`client/_transport.py`](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/src/mcp/client/_transport.py)). **There is no `GetSessionIdCallback` in v2** — the session ID is internal (`MCP_SESSION_ID = "mcp-session-id"`; extracted from the initialize response by `_maybe_extract_session_id_from_response`, re-injected into every subsequent request header automatically). If you need to read it, you must intercept httpx response events yourself.
- Same-origin redirects only (same scheme+host+port, or http→https); `follow_redirects` is ignored.
- `mcp-types` is now a separate workspace package wire-locked `mcp-types==2.3.0`, with `mcp.types` kept as an alias shim. Dependency floors: `httpx2>=2.10.0`, `pydantic>=2.12.0`, `anyio>=4.9`, `jsonschema>=4.20.0`, `pyjwt[crypto]>=2.10.1`.

High-level client (new in 2.x) — canonical snippet from `main`'s README:

```python
import asyncio
from mcp import Client

async def main() -> None:
    async with Client("http://localhost:8000/mcp") as client:
        result = await client.call_tool("add", {"a": 1, "b": 2})
        print(result.structured_content)  # {'result': 3}

asyncio.run(main())
```

- `Client` is a dataclass with `raise_exceptions: bool = False`, `read_timeout_seconds: float | None`, and **`mode: ConnectMode = "auto"`** — `"auto"` probes the **`server/discover`** RPC (the 2026-07-28 stateless protocol) and falls back to the classic `initialize` handshake; `"legacy"` forces the classic handshake. So the current SDK already speaks both protocol eras.
- `__post_init__` maps a bare URL string to `streamable_http_client(url)` with **no header/auth hook** — for authenticated streaming servers, build the transport yourself:

```python
import httpx2
from mcp.client.streamable_http import streamable_http_client
from mcp import Client

transport = streamable_http_client(
    "https://example.com/mcp",
    http_client=httpx2.AsyncClient(
        headers={"Authorization": "Bearer <token>"},
        timeout=httpx2.Timeout(30.0, read=300.0),
    ),
)
async with Client(transport) as client:
    ...
```

- Low-level session pattern (from [`examples/snippets/clients/streamable_basic.py`](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/examples/snippets/clients/streamable_basic.py)):

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async with streamable_http_client("http://localhost:8000/mcp") as (read_stream, write_stream):
    async with ClientSession(read_stream, write_stream) as session:
        await session.initialize()
        tools = await session.list_tools()
        print(f"Available tools: {[tool.name for tool in tools.tools]}")
```

- The classic handshake under the hood: `session.initialize()` POSTs `InitializeRequest`, the transport captures `Mcp-Session-Id` off the response, then posts `notifications/initialized`; the standalone GET SSE stream starts only on the initialized notification (`if self._is_initialized_notification(message): start_get_stream()`).

### 5.2 `ClientSession` API

- `ClientSession.__init__` (2.x): `read_stream, write_stream, read_timeout_seconds: float | None = None, sampling_callback, elicitation_callback, list_roots_callback, logging_callback, message_handler, client_info, log_level, sampling_capabilities, extensions, result_claims, notification_bindings, dispatcher`. In 1.30.0 the equivalent takes `read_timeout_seconds: timedelta | None` (**v2 changed the type from `timedelta` to `float` seconds**) and streams are positional/required.
- **`list_tools(params=None) -> types.ListToolsResult`** (`ListToolsResult {tools, next_cursor/nextCursor, meta}`). In 1.x: `list_tools(cursor=None)`.
- **`call_tool`** (2.x, verbatim):

```python
async def call_tool(
    self,
    name: str,
    arguments: dict[str, Any] | None = None,
    read_timeout_seconds: float | None = None,
    progress_callback: ProgressFnT | None = None,
    *,
    input_responses: types.InputResponses | None = None,
    request_state: str | None = None,
    meta: RequestParamsMeta | None = None,
    allow_input_required: bool = False,
    allow_claimed: bool = False,
) -> types.CallToolResult | types.InputRequiredResult | types.Result:
```

  1.x subset: `call_tool(name, arguments, read_timeout_seconds: timedelta | None = None, progress_callback=None) -> types.CallToolResult`. **There is no `call_tool_raw`** in either version; the 2.x raw/bypass knobs are the `allow_input_required` / `allow_claimed` keyword flags.
- Return type `CallToolResult`:

```python
content: list[ContentBlock]
is_error: bool | None        # alias "isError"; treat as bool(result.is_error)
structured_content: dict[str, Any] | None   # alias "structuredContent"
```

  with `ContentBlock = TextContent | ImageContent | AudioContent | ResourceLink | EmbeddedResource` (Audio/ResourceLink are 2.x-era additions).
- **`Tool` wire model (current `mcp-types`):** `name: str`, `title: str | None`, `description`, `input_schema` (alias `inputSchema`; required, `type: "object"` root JSON Schema), `output_schema` (alias `outputSchema`, optional), `annotations: ToolAnnotations`, `meta` (alias `_meta`), `execution`, `icons`. **`outputSchema` does exist in current versions** (it is only absent in very old ones), and the 2.x session validates results against the declared output schema client-side.
- `initialize()` negotiates `LATEST_PROTOCOL_VERSION`; `session.initialize()` is explicit in the legacy flow and skipped when `Client` operates in `"auto"`→modern mode.

### 5.3 Timeouts

- Three layers: (1) HTTP transport timeout — 30 s non-read / **300 s read** by default, settable in v1 via `timeout=` / `sse_read_timeout=` and in v2 via your own httpx2 client's `Timeout(30.0, read=…)`; (2) session-wide read timeout — `read_timeout_seconds` on `ClientSession`/`Client`, **default `None` = unbounded session-level read timeout** (`anyio.fail_after(None)` in v1 = wait indefinitely); (3) per-request override — `read_timeout_seconds=` on `call_tool`/other methods ("request read timeout takes precedence over the session read timeout").
- **Tool-call timeout does NOT default to 60 s.** Effective v1 default: unbounded session timeout bounded by the HTTP read timeout (**300 s**), then `httpx.ReadTimeout` — surfacing inside an ExceptionGroup at the transport context exit. In 2.x, request timeouts are converted into a clean exception by the session: `send_request` docstring *"Raises: MCPError: Error response, read timeout, or connection closed."*
- v1 timeout error (from [`shared/session.py`](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/v1.30.0/src/mcp/shared/session.py)): `McpError(ErrorData(code=408 /* REQUEST_TIMEOUT */, message="Timed out while waiting for response to {Request}. Waited {N} seconds."))`.

### 5.4 Error/exception semantics — the sharp edges

1. **`MCPError`** (2.x; named `McpError` in 1.x): `MCPError(code, message, data=None)` with `.code/.message/.data` and `.error: ErrorData`. Raised by `send_request` on (a) JSON-RPC error responses, (b) request read timeouts, (c) connection closed. 1.x used `McpError(error: ErrorData)` — access via `exc.error.code`.
2. **Tool-execution failures are NOT exceptions** — they arrive as normal results with `is_error=True` and the message in `content[0].text` (per the spec's two error channels, §3.6); protocol-level errors raise `MCPError`.
3. **anyio ExceptionGroup wrapping.** Both versions run the transport inside `anyio.create_task_group()`; httpx-level failures raised in spawned POST/writer tasks (`ConnectError`, `ConnectTimeout`, `ReadTimeout`, `HTTPStatusError` from `raise_for_status()`) are held by the task group and re-raised **when the transport context manager exits**, wrapped in an `ExceptionGroup`/`BaseExceptionGroup`. Catch with `except* httpx.ConnectError:` (or unwrap `excgroup.exceptions`) around the whole `async with streamable_http_client(...)` / `Client(...)` block — initial-connect failures (DNS, TLS) surface at context-exit, not inside `session.initialize()`.
4. **Session expiry / server restart (404)** — verified in v1.9.4, v1.30.0, and `main`: **no auto-reinitialize anywhere.** A 404 on a POST carrying a session ID is converted into the pending request's error: v1 → `McpError` with `code=32600`, message **"Session terminated"**; v2 → `MCPError(code=INVALID_REQUEST /* -32600 */, message="Session terminated")`; a 404 **without** a session ID → `code=METHOD_NOT_FOUND, message="Not Found"`. Recovery is caller-side: exit the context, rebuild the transport (a new `initialize` mints a new session ID).
5. **The GET SSE stream is deliberately non-fatal**: `except Exception: logger.debug("GET stream error (non-fatal)")` with auto-reconnect capped at `MAX_RECONNECTION_ATTEMPTS = 2` (`DEFAULT_RECONNECTION_DELAY_MS = 1000`). Losing that background stream does not fail in-flight requests (responses ride POST streams); after 2 failed attempts it stays down until re-entry.

### 5.5 Auth in the official SDK

- [`mcp/client/auth`](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/src/mcp/client/auth/__init__.py) exports `OAuthClientProvider`, `AuthorizationCodeResult`, `TokenStorage`, `PKCEParameters`, `OAuthFlowError`, `OAuthTokenError`, `OAuthRegistrationError`. `OAuthClientProvider` (an `httpx(2).Auth`) implements the **full OAuth 2.1 authorization-code flow with PKCE**: protected-resource + AS metadata discovery, (dynamic) client registration, 401-triggered flow restart, 403 `insufficient_scope` step-up, token exchange and automatic refresh; signature: `OAuthClientProvider(server_url, client_metadata: OAuthClientMetadata, storage: TokenStorage, redirect_handler=None, callback_handler=None, client_metadata_url=None, validate_resource_url=None)`. 2.x additions in `mcp/client/auth/extensions/`: `ClientCredentialsOAuthProvider` and `PrivateKeyJWTOAuthProvider`.
- **`BearerAuthProvider` does not exist in the official SDK** (that class is FastMCP's). Simple token auth = headers or a custom `httpx(2).Auth`: 1.x `streamablehttp_client(url, headers={"Authorization": "Bearer …"}), auth=custom`; 2.x as in §5.1 (header dict on the httpx2 client).

---

## 6. FastMCP client API — where it differs

Primary sources: [`fastmcp_slim/fastmcp/client/client.py`](https://raw.githubusercontent.com/PrefectHQ/fastmcp/main/fastmcp_slim/fastmcp/client/client.py), [`client/transports/http.py`](https://raw.githubusercontent.com/PrefectHQ/fastmcp/main/fastmcp_slim/fastmcp/client/transports/http.py), [`client/mixins/tools.py`](https://raw.githubusercontent.com/PrefectHQ/fastmcp/main/fastmcp_slim/fastmcp/client/mixins/tools.py), [`client/auth/bearer.py`](https://raw.githubusercontent.com/PrefectHQ/fastmcp/main/fastmcp_slim/fastmcp/client/auth/bearer.py) (repo `PrefectHQ/fastmcp`; docs [gofastmcp.com](https://gofastmcp.com/clients/client)).

Corrections to common premises: repo moved to `PrefectHQ/fastmcp`; `fastmcp.dev` is an unrelated MCP directory site, not the docs.

### 6.1 Transports and connection

- `Client(transport)` accepts a `ClientTransport`, a `FastMCP` server instance (→ **in-memory**, zero networking), a `Path` (stdio), a config dict (→ multi-server composite client with `servername_toolname` namespacing), or a **URL string**: HTTP URLs infer `StreamableHttpTransport`, URLs ending `/sse` infer `SSETransport`, "For HTTP URLs, they are assumed to be Streamable HTTP URLs unless they end in `/sse`." **There is no `Client.streamable_http(url)` classmethod** — URL-string inference is the shortcut.
- `StreamableHttpTransport(url, headers=None, auth=None, httpx_client_factory=None, verify=None)` — **no `sse_read_timeout` in 4.x** (that parameter existed in v2.x; the timeout knob moved to `Client(timeout=…)`, which becomes the session's `read_timeout_seconds`, HTTP layer `Timeout(30.0, read=read_timeout_seconds)`). `verify` accepts `False` (skip TLS verification), a CA-bundle path, or an `ssl.SSLContext`. The URL path is used verbatim ("Don't modify the URL path - respect the exact URL provided by the user"), and a non-http(s) scheme raises `ValueError("Invalid HTTP/S URL provided for Streamable HTTP.")`.
- `Client.__init__` knobs: `timeout` (per-request read timeout; float/timedelta), `init_timeout` (handshake; "Set to 0 to disable"), `auto_initialize: bool = True`, `auth`, `verify`, `mode: ConnectMode = "auto"` (**4.0 protocol-era negotiation: probes `server/discover` / 2026-07-28, falls back to the legacy `initialize` handshake; `"legacy"` forces classic**), `input_required_max_rounds` (SEP-2322), `cache: CacheConfig | bool | None` (SEP-2549 response caching), `extensions` (SEP-2133). **There is no `Timeouts` dataclass in any 2.9–4.1 version.**
- The context manager is **reentrant/concurrent** (reference-counted; a background session task handles calls): `async with client:` → handshake → populates `client.protocol_version`, `server_info`, `server_capabilities`, `instructions` (reset to `None` on disconnect). `client.new()` clones config with fresh session state.
- `get_session_id()` is a **transport** method (`self._session_id`, captured from the server's `mcp-session-id` response header via an httpx event hook — because SDK v2 no longer exposes the callback); it exists only for legacy-era connections ("the 2026-07-28 modern protocol is sessionless").
- Extras: `set_roots()`, `set_sampling_callback()`, `set_elicitation_callback()`, `set_logging_level()` ("Handshake-era servers only… raises RuntimeError on MCP 2026-07-28 connections"), `ping()`, `cancel(request_id, reason=None)`.

### 6.2 Tool listing

- `list_tools(max_pages=250, *, cache_mode="use") -> list[mcp_types.Tool]` — **auto-paginates** (raises `RuntimeError` on the 250-page cap); cache modes `"use" | "refresh" | "bypass"`; raw/paged variant `list_tools_mcp(*, cursor=None, cache_mode="use") -> mcp_types.ListToolsResult`.
- Tools are standard `mcp_types.Tool` with snake_case properties: `input_schema`, `output_schema`, plus `title`, `description`, `annotations`, `meta`.
- **FastMCP server-specific metadata** arrives in `Tool._meta["fastmcp"]`: `{"tags": [...sorted], "version": ...}` (`FastMCPComponent.get_meta()`); the `enabled` state is **NOT client-visible** in 4.x (it lives in an internal `_internal` key that is filtered out; v2.x did expose `enabled: bool` server-side).

### 6.3 Tool calling and errors

```python
async def call_tool(
    self, name, arguments=None, *,
    version=None, timeout=None, progress_handler=None,
    raise_on_error: bool = True, meta=None,
) -> CallToolResult
```

- Return is FastMCP's own dataclass:

```python
@dataclass
class CallToolResult:
    content: list[mcp_types.ContentBlock]
    structured_content: dict[str, Any] | None
    meta: dict[str, Any] | None
    data: Any = None        # hydrated from output_schema; None if absent/failed
    is_error: bool = False
```

- **Key difference from the official SDK:** `result.data` is "fully hydrated Python objects including complex types like datetimes and UUIDs, reconstructed from the server's output schema" (JSON-schema→pydantic type-adapter validation), and FastMCP's `{"result": <primitive>}` wrapper is auto-unwrapped via the server-sent `meta["fastmcp"]["wrap_result"]` flag or an `x-fastmcp-wrap-result` schema key.
- **Errors raise by default:** "Unlike `call_tool_mcp`, this method raises a `ToolError` if the tool call results in an error" — `fastmcp.exceptions.ToolError(msg)` where `msg = result.content[0].text` when present, else `f"Tool '{name}' returned an error"`. Set `raise_on_error=False` to inspect `result.is_error` yourself. Protocol/timeout failures (`MCPError`) propagate separately from either variant.
- Raw variant: `call_tool_mcp(name, arguments, progress_handler=None, timeout=None, meta=None) -> mcp_types.CallToolResult` (never raises on tool errors; surfaces `isError`). **`call_tool_raw()` / a `_return_raw=` parameter do not exist** in any checked release (v2.9.0 → 4.1.0).
- History: ≤2.9 `call_tool()` returned the content list directly and raised `ToolError`; `CallToolResult` arrived in 2.10.0; 4.x added `structured_content`/`meta`/`raise_on_error`/`version`/SEP-2322 input-required rounds.

### 6.4 Auth

- `auth` param accepts `httpx2.Auth | Literal["oauth"] | str | None` (on both `Client` and HTTP transports). Resolution: `auth="oauth"` → built-in `OAuth` flow; `"oauth"`'s helper `fastmcp.client.auth.OAuth(OAuthClientProvider)` takes `scopes`, `client_name`, `token_storage` (pluggable `AsyncKeyValue`, in-memory default, `DiskStore` + Fernet encryption), `callback_port`, and `client_metadata_url` (CIMD, 3.0+); a bare `str` token → `BearerAuth(token)`; anything else passes through as an `httpx2.Auth`.
- **`BearerAuth`** (whole file): `class BearerAuth(httpx2.Auth): def __init__(self, token: str): self.token = SecretStr(token)`; `auth_flow` sets `request.headers["Authorization"] = f"Bearer {token}"`. With a string token "do not include the `Bearer` prefix. FastMCP will add it for you."
- **API-key auth is done with transport `headers`, not `auth`:** `StreamableHttpTransport("https://host/mcp", headers={"X-API-Key": "<key>"})` (or `{"Authorization": "Bearer <token>"}`). FastMCP enforces `follow_redirects=True` and relies on httpx stripping `Authorization` cross-origin redirects; because it's `httpx2`, third-party `httpx.Auth` classes do not drop in unchanged.
- Client-side OAuth: `auth="oauth"` → zero-config OAuth 2.1 + PKCE with cached tokens, auto-registration, local callback server, refresh. Server-issued credential flows (`ClientCredentialsOAuthProvider`, `PrivateKeyJWTOAuthProvider`) exist for browser-less clients.

### 6.5 Disconnect / reconnect semantics

- **No auto-reconnect.** No reconnection logic exists in client or transports; a background-session failure is surfaced via `_await_with_session_monitoring` as `RuntimeError("Client failed to connect: …")` rather than a hang. Recovery = re-enter `async with client:` (session state fully reset).
- Keepalive: only stdio (`StdioTransport(..., keep_alive=True)` default — "maintain sessions across multiple client contexts by default"). HTTP transport: none at the FastMCP layer (spec-level SSE keepalive comments, §2.9).
- Disconnect: last context exit → stop task → transport teardown; "Normally disconnects complete in <100ms" (safety-net `client_disconnect_timeout` setting); `client.close()` forces disconnect + `transport.close()`.

---

## 7. A per-run connection in practice

Combining spec + SDK behavior, for a connection used for one run then torn down:

**Setup cost.**
- *Classic protocol (initialize-era servers, the vast majority today):* POST `initialize` (1 round trip) + POST `notifications/initialized` (1 round trip, 202) — and an optional GET SSE connection for server-initiated messages (opens only after the initialized notification). All further calls are single POSTs reusing the httpx connection pool, with `Mcp-Session-Id` + `MCP-Protocol-Version` echoed. Net: ~2 extra round trips per connection; per-call afterward = 1 POST.
- *2026-07-28 stateless protocol:* **zero handshake** — every request self-describes (protocol version + capabilities in `_meta`, mirrored headers); `server/discover` is an optional up-front capability probe. No session ID, so per-run connection reuse is purely an optimization of the httpx pool, not a protocol need.

**Timers at rest.**
- HTTP layer: 30 s connect/write/pool, **300 s read** (both SDKs' defaults; the read phase is what governs a long streaming/tool response and also the idle GET stream).
- Session-level request read timeout defaults to **None (unbounded)** in both SDKs; per-call or session-level `read_timeout_seconds` is the right knob for a per-run bridge. v1 wraps its timeout as `McpError(408 REQUEST_TIMEOUT)`; v2 raises `MCPError`.

**Keepalive.**
- No HTTP-level keepalive in the SDKs. The spec only encourages SSE comment keepalives for long-lived streams (2026-07-28 `subscriptions/listen`; earlier revisions: server MAY close connections with an SSE `retry` field for client polling). For ordinary request-scoped POST streams nothing is needed — they terminate with the response. A tool call longer than the read timeout will die at 300 s unless you raise the timeout.

**Disconnect semantics.**
- Clean shutdown: context exit → (classic protocol) HTTP DELETE with `Mcp-Session-Id` when `terminate_on_close=True` (default; server MAY refuse with 405 — non-fatal); (v2) DELETE sent by the transport on close.
- Mid-run drop: SSE stream drop is non-fatal for in-flight POST requests at the SDK layer (auto-reconnect attempts capped at 2, 1 s delay); under the 2026-07-28 protocol there is **no recovery** — "A broken response stream loses the in-flight request; clients MUST re-issue it as a new request."
- Server restart / session expiry: 404 on a session-bearing POST → `MCPError(code=-32600, message="Session terminated")`, **SDK will not re-initialize** — the caller must rebuild the connection. A per-run design sidesteps this entirely: each run's connection starts with a fresh handshake (or, stateless-era, no handshake at all); a server restart between runs is invisible.
- Background GET stream (classic protocol, 2.x SDK): non-fatal, capped reconnect; its loss does not affect single-shot tools/list + tools/call flows (responses ride the request's own POST stream).

**Cost summary per run.** HTTP(S) + 2 round trips (initialize/initialized) + one POST per tool call on a pooled connection; teardown = 1 DELETE. Stateless-era: 0 setup round trips. The meaningful per-run cost is not the handshake — it's tool-list acquisition (1 POST `tools/list`) and any slow tool calls (bounded by the read timeout you configure).

---

## 8. Implications for this repo (client-only, Streamable HTTP, #119–#121)

- **Protocol-era choice must be explicit in the spec.** Current ecosystems are split-brained: the 2025-03-26→2025-11-25 "initialize + session" shape is what essentially every deployed server speaks, while 2026-07-28 is the published future (stateless, sessionless, `server/discover`). Both the official SDK 2.x (`mode="auto"`) and FastMCP 4.x handle both eras; a client implementation should plan for era negotiation, and treat the classic shape as the compatibility baseline.
- **SDK choice is effectively a v2-vs-v1 API choice.** `uv add mcp` today yields 2.3.0 — new `Client`/`streamable_http_client` API, `httpx2`, `MCPError`, no public session-id accessor. The classic `streamablehttp_client(...)` snippet (all current tutorials/blog posts) is the **deprecated 1.x wrapper**. FastMCP 4.1.0 (also on `mcp` v2 internals) gives auto-paginated `list_tools`, hydrated `CallToolResult.data`, and `BearerAuth`/`auth="oauth"` conveniences; it differs meaningfully from the raw SDK (which forces hand-rolled httpx2 clients for auth/headers and returns raw `CallToolResult`).
- **Tool → DSPy descriptor conversion (#119):** `Tool.name`/`.description`/`input_schema` map cleanly; `input_schema` is a JSON-Schema `type:"object"` on the wire (any 2020-12 keywords allowed in the latest spec), so DSPy descriptor building must tolerate full JSON Schema (nested objects, `oneOf`/`anyOf`, `$ref`s), or adopt a narrowing policy (e.g. flatten to primitive-typed required args with a JSON-string escape hatch).
- **Error semantics for the agent loop (#121):** tool-execution failures should become model-facing observations (matches CLAUDE.md decision #12) — with the raw SDK you branch on `result.is_error` and use `content[0].text`; with FastMCP you catch `ToolError`. Protocol/timeout failures raise `MCPError`; httpx-level failures surface as `ExceptionGroup`s at transport-context exit (`except*` needed). Any timeout you want must be explicit — defaults are unbounded session-side / 300 s HTTP-side.
- **Connection lifetime (#121):** per-run connection is well-supported and simple (context-manager per run, ~2 round-trip setup under the classic handshake, zero under stateless, DELETE teardown), and it avoids the only serious failure mode the SDK won't handle for you — **404 "Session terminated" after a server restart, which no SDK recovers from automatically**. A session pool (SandboxManager precedent) buys re-connection reuse only under the classic protocol and must be paired with 404-driven rebuild logic; under the 2026-07-28 protocol a pool degenerates to an httpx pool.
- **Python/runtime compatibility:** both SDKs require Python ≥ 3.10 (backend is 3.12 ✓); the SDKs pull `httpx2` (Pydantic-stewarded httpx continuation), which coexists fine with the backend's use of `httpx` (test suite only).

---

## Appendix: source index

- Spec transports: [2024-11-05](https://modelcontextprotocol.io/specification/2024-11-05/basic/transports) · [2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) · [2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports) · [2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) · [2026-07-28 streamable-http](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http.md)
- Spec changelogs: [2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/changelog) · [2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/changelog) · [2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/changelog)
- Spec auth: [2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26/basic/authorization) · [2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization) · [2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/index.md)
- Spec tools: [2025-06-18 server/tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools.md)
- Official SDK: [repo](https://github.com/modelcontextprotocol/python-sdk) · [README (main)](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/README.md) · [VERSIONING.md](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/VERSIONING.md) · [`streamable_http.py` (main)](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/src/mcp/client/streamable_http.py) · [v1.30.0 `streamable_http.py`](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/v1.30.0/src/mcp/client/streamable_http.py) · [`session.py` (main)](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/src/mcp/client/session.py) · [`client.py` (main)](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/src/mcp/client/client.py) · [`_httpx_utils.py`](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/src/mcp/shared/_httpx_utils.py) · [`auth/`](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/src/mcp/client/auth/__init__.py) · [streamable_basic example](https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/examples/snippets/clients/streamable_basic.py) · [PyPI `mcp`](https://pypi.org/project/mcp/)
- FastMCP: [repo](https://github.com/PrefectHQ/fastmcp) · [`client/client.py` (main)](https://raw.githubusercontent.com/PrefectHQ/fastmcp/main/fastmcp_slim/fastmcp/client/client.py) · [`client/transports/http.py`](https://raw.githubusercontent.com/PrefectHQ/fastmcp/main/fastmcp_slim/fastmcp/client/transports/http.py) · [`client/mixins/tools.py`](https://raw.githubusercontent.com/PrefectHQ/fastmcp/main/fastmcp_slim/fastmcp/client/mixins/tools.py) · [`client/auth/bearer.py`](https://raw.githubusercontent.com/PrefectHQ/fastmcp/main/fastmcp_slim/fastmcp/client/auth/bearer.py) · docs: [clients/client](https://gofastmcp.com/clients/client) · [clients/tools](https://gofastmcp.com/clients/tools) · [clients/auth/bearer](https://gofastmcp.com/clients/auth/bearer) · [clients/auth/oauth](https://gofastmcp.com/clients/auth/oauth) · [clients/transports](https://gofastmcp.com/clients/transports) · [PyPI `fastmcp`](https://pypi.org/project/fastmcp/)
- Other: [PyPI `httpx2`](https://pypi.org/project/httpx2/) · [modelcontextprotocol.io/llms.txt](https://modelcontextprotocol.io/llms.txt) · [modelcontextprotocol/ext-auth](https://github.com/modelcontextprotocol/ext-auth)