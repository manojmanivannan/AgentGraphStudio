# MCP Streamable HTTP Transport + Python Client SDKs — Factual State

> Research note (2026-10-11). Companion to
> [mcp-client-integration-patterns.md](./mcp-client-integration-patterns.md): that note covers
> how frameworks *integrate* MCP; this one covers the **transport and SDK-level facts** the
> `mcp-tools` branch needs — Streamable HTTP wire semantics, the authorization model, the
> official `mcp` Python SDK client API, the FastMCP client, and the practical cost of
> opening/reusing connections per agent run. All claims are from primary sources (spec text
> at modelcontextprotocol.io, the `modelcontextprotocol/python-sdk` source tree, PyPI
> metadata, FastMCP source/docs); protocol revisions relied on: **2026-07-28 (current),
> 2025-11-25, 2025-06-18, 2025-03-26**; SDK versions relied on: `mcp` 1.30.0 and 2.3.0,
> `fastmcp` 4.1.0 (all verified current as of this date). Not committed to git.

---

## Summary

1. **There is a newer protocol revision than most material assumes.** The newest published
   spec revision is **2026-07-28** (verified against the docs index, the GitHub spec tree,
   and release tags); it is a *breaking rewrite* of Streamable HTTP: GET streams,
   protocol-level sessions (`Mcp-Session-Id`), `Last-Event-ID` resumability, and the
   `ping` utility are **all removed**. The 2026-07-28 opening notice says clients "must
   ensure they handle backwards compatibility correctly," and the spec now splits the world
   into "modern" (POST-only, stateless, per-request versioning) and "legacy"
   (`initialize`-handshake, `2025-11-25` and earlier) behavior.
2. **Everything deployed in practice today still speaks the legacy shape**, so the
   implementation surface that matters is the 2025-x semantics: one POST endpoint that MAY
   return `application/json` or `text/event-stream`, optional server-granted
   `MCP-Session-Id` echoed on every request, session loss surfacing as **HTTP 404 → the
   client MUST re-initialize**, HTTP DELETE for explicit termination, and a mandatory
   `MCP-Protocol-Version` header on all post-initialize requests.
3. **Authorization is OPTIONAL in the spec, and OAuth 2.1 is not required to run a server.**
   The gating language is transport-based, not deployment-based: HTTP-based implementations
   "SHOULD conform," stdio implementations "SHOULD NOT." A bearer-token/API-key header
   server is not *prohibited* — but there is no "custom authorization scheme" provision in
   the spec, so non-OAuth auth is outside the conformant mechanism, and an MCP client's
   OAuth discovery flow (401 + `WWW-Authenticate` → RFC 9728 resource metadata → AS
   metadata) has nothing to discover against such a server. Clients sending a raw
   `Authorization: Bearer <token>` header to a non-OAuth server are doing something the
   spec neither endorses nor forbids; virtually every real tool integration does it.
4. **The official Python SDK now has two parallel release lines**, and this is the single
   biggest SDK-level decision: **1.x** (current 1.30.0, 2026-09-07) is the API the whole
   ecosystem targets (`streamablehttp_client`, camelCase `Tool`/`CallToolResult`, 3-tuple
   yield with `get_session_id`); **2.x** (current 2.3.0, 2026-10-02) is a breaking rewrite
   implementing the 2026 wire — snake_case models in a split `mcp-types` package, `httpx2`,
   a high-level `Client` with `server/discover` auto-negotiation, and a 2-tuple (no
   session id) transport. FastMCP 4.x wraps SDK v2 and negotiates both eras.
5. **Tool-call errors do not raise in the official SDK.** `ClientSession.call_tool()`
   returns `CallToolResult(content=[...], structuredContent=..., isError=...)`; tool
   execution failures arrive in-band as `isError=True`. It raises `McpError` only for
   protocol-level problems (unknown tool, transport/HTTP errors, client-side read timeouts
   synthesized as code 408), plus `RuntimeError` when `structuredContent` fails the tool's
   declared `outputSchema`. Frameworks differ in what they do on top: FastMCP's
   `Client.call_tool()` raises `ToolError` by default (`raise_on_error=False` to opt out);
   langchain-mcp-adapters converts `isError` to a model-visible error `ToolMessage`.
6. **Error surfacing from the transport is SDK-version-dependent and partly ExceptionGroup-
   shaped.** In the 1.x line the POST handler runs inside the transport's `anyio` task
   group and calls `response.raise_for_status()`, so `httpx.ConnectError`,
   `httpx.HTTPStatusError`, and read timeouts typically reach the caller wrapped in a
   `BaseExceptionGroup` at the point the context manager exits or the first session call
   awaits (inferred from source structure, not executed — flagged). In the 2.x line
   non-2xx responses are synthesized into JSON-RPC errors on the read stream and surface
   as `MCPError` (404 with no session → `METHOD_NOT_FOUND`; 404 with a session →
   `INVALID_REQUEST` "Session terminated"); there is no `raise_for_status` on the request
   path.
7. **Default timeouts are 30 s connect/write/pool and 300 s read (`sse_read_timeout`)** in
   the official SDK (`MCP_DEFAULT_TIMEOUT = 30.0`, `MCP_DEFAULT_SSE_READ_TIMEOUT = 300.0`),
   the same defaults when `streamablehttp_client(timeout=30, sse_read_timeout=300)` is
   passed explicitly. In 1.x the transport-level timeout/auth params are deprecated in
   favor of configuring the `httpx.AsyncClient` and passing it as `http_client=`;
   custom headers (including `Authorization`) therefore live on the httpx client, merged
   per-request with MCP-specific headers (`mcp-session-id`, `mcp-protocol-version`) that
   take precedence.
8. **FastMCP is the richer client surface and is now the actively maintained "batteries
   included" layer — but the project has moved and renumbered.** `jlowin/fastmcp` redirects
   to **PrefectHQ/fastmcp**, docs live at gofastmcp.com, and the current line is **4.x
   (4.1.0, 2026-10-08)** — 2.x (last release 2.14.7, 2026-04-13) and 3.x (maintenance)
   predate it. FastMCP `Client` wraps the official `ClientSession` (a superset, not a
   fork): URL inference, reentrant connection context, auto-pagination of `list_tools`,
   structured-output hydration (`.data`), `BearerAuth`/`OAuth` helpers, and both
   `call_tool()` (raises `ToolError`, returns a hydrated `CallToolResult` dataclass) and
   `call_tool_mcp()` (returns the raw SDK `CallToolResult`, never raises on tool error).
   FastMCP's client-side `Tool` has **no** `tags`/`enabled` attributes; server-side tags
   ride in `_meta["fastmcp"]["tags"]` (2.x: `_fastmcp`), and a disabled tool simply
   disappears from `tools/list`.
9. **Per-run connection cost is small on Streamable HTTP and there is no documented
   millisecond figure in any primary source.** A connection = TCP(+TLS) + one HTTP POST
   `initialize` + one `notifications/initialized` POST (legacy), or on modern servers **no
   handshake at all**. No spec- or SDK-mandated keepalive exists client-side: `ping` is
   optional (and removed in 2026-07-28), the SDK has no heartbeat, so a per-run
   open-close cycle with no idle keepalive is the natural fit for AgentGraphStudio's
   per-run worker. The SDK does not auto-reinitialize on 404 despite the spec's MUST —
   callers must catch "Session terminated" and re-run the handshake themselves. One
   connection is freely reusable across sequential `tools/call`s within its context
   manager; each call is an independent POST on the pooled httpx client.
10. **Session semantics: a stale `MCP-Session-Id` yields 404, not a distinct error**, and
    the spec treats 404 as "session ended" (`terminate_session` DELETE failures and
    server-side termination are indistinguishable over the wire). In 1.x this maps to a
    JSON-RPC error `{code: 32600, message: "Session terminated"}`; clients that need
    durability must treat any 404 / "Session terminated" as "re-initialize" (which the
    spec actually requires). The SDK's GET-stream resumability machinery reconnects with
    `Last-Event-ID` (up to 2 attempts, 1 s default delay) for request SSE streams; redelivery
    is strictly per-stream and gone entirely in 2026-07-28.

---

## Version landscape you must design against

| Artifact | Current (2026-10-11) | Notes |
|---|---|---|
| Spec revision | **2026-07-28** | Revisions: 2024-11-05 → 2025-03-26 → 2025-06-18 → 2025-11-25 → 2026-07-28 (+ `draft`). Verified via [llms.txt](https://modelcontextprotocol.io/llms.txt), GitHub `docs/specification/` dirs, and release tags |
| `mcp` (official SDK) 1.x | **1.30.0** (2026-09-07) | `streamablehttp_client` / camelCase models; what most frameworks and docs target today ([PyPI](https://pypi.org/pypi/mcp/json)) |
| `mcp` 2.x | **2.3.0** (2026-10-02) | Breaking rewrite: snake_case (`mcp-types`), `httpx2`, `Client`, `server/discover`; first 2.0.0 on 2026-07-28 (same day as the spec revision) |
| `fastmcp` | **4.1.0** (2026-10-08) | PrefectHQ/fastmcp (moved from jlowin); wraps SDK v2; 2.x last release 2.14.7 (2026-04-13), 3.x maintenance ([PyPI](https://pypi.org/pypi/fastmcp/json)) |
| HTTP+SSE transport | Deprecated since 2025-03-26 | "New implementations SHOULD NOT adopt it" ([deprecated registry](https://modelcontextprotocol.io/specification/2026-07-28/deprecated)) |

Note: **modelcontextprotocol.info is a third-party community mirror** (missing 2026-07-28);
cite modelcontextprotocol.io (or the `modelcontextprotocol/modelcontextprotocol` GitHub
repo) as the authoritative spec source.

---

## 1. Streamable HTTP transport

### 1.1 Legacy shape (2025-03-26 → 2025-11-25) — what real servers speak today

Normative page: [2025-11-25 basic/transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) (identical structure at 2025-06-18 and 2025-03-26; the 2025-11-25 revisions relevant here are [listed in its changelog](https://modelcontextprotocol.io/specification/2025-11-25/changelog)).

**Single endpoint.** "The server **MUST** provide a single HTTP endpoint path (hereafter
referred to as the **MCP endpoint**) that supports both POST and GET methods."

**POST semantics.** Every JSON-RPC message the client sends is its own POST. The client
MUST send `Accept: application/json, text/event-stream`; the body MUST be a single
JSON-RPC request, notification, or response. For a notification/response the server MUST
return `202 Accepted` with no body (or an HTTP error, e.g. 400). For a request the server
**MUST** respond with `Content-Type: text/event-stream` (an SSE stream carrying
notifications then the response) **or** `Content-Type: application/json` (one JSON
object) — "The client **MUST** support both these cases." Whether a given call streams is
the server's per-request choice; after the response the server SHOULD close the SSE
stream. "The server **MUST** send each of its JSON-RPC messages on only one of the
connected streams; … it **MUST NOT** broadcast the same message across multiple streams."

**GET semantics.** The client MAY open a GET SSE stream for server-initiated messages;
the server "MUST either return `Content-Type: text/event-stream` … or else return HTTP
405 Method Not Allowed" — GET is entirely optional for servers, and on it the server
MUST NOT send responses except resumability redelivery.

**Sessions ([#session-management](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#session-management)).**
"An `MCP-Session-Id` [header]… **MAY** assign a session ID at initialization time" —
sessions are optional and server-granted; the header name is written `McP-Session-Id` in
2025-06-18 and `MCP-Session-Id` in 2025-11-25 (HTTP header names are case-insensitive;
the rename is editorial). Rules:
- If assigned, the client MUST echo it on **every** subsequent request; servers
  requiring it SHOULD answer requests without it with HTTP 400.
- The server MAY terminate at any time, after which it MUST answer requests carrying
  that id with **HTTP 404 Not Found**.
- "When a client receives HTTP 404 …, it **MUST** start a new session by sending a new
  `InitializeRequest` without a session ID."
- Clients that are done SHOULD send **HTTP DELETE** to the endpoint with the
  `MCP-Session-Id` header; the server MAY refuse with 405 ("does not allow clients to
  terminate sessions"). What a *successful* DELETE returns is unspecified.
- The id SHOULD be "globally unique and cryptographically secure" and MUST be visible
  ASCII (0x21–0x7E). 2025-11-25 adds a client MUST to handle it securely (session
  hijacking mitigations).

**Resumability ([#resumability-and-redelivery](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#resumability-and-redelivery)).**
Servers MAY attach SSE event `id`s (globally unique per session/stream); a client may
resume a broken stream via GET with `Last-Event-ID`, and the server MAY replay "messages
that would have been sent after the last event ID, *on the stream that was disconnected*"
— redelivery is strictly per-stream. 2025-11-25 additions (SEP-1699 polling): servers
SHOULD send an empty-data "priming" SSE event right away; servers MAY drop the *TCP
connection* at any time without terminating the *SSE stream*, with a `retry` field the
client MUST honor before reconnecting; resumption is always via GET with
`Last-Event-ID`, regardless of whether the original stream came from POST or GET.

**Protocol version header.** "If using HTTP, the client **MUST** include the
`MCP-Protocol-Version: <protocol-version>` HTTP header on all subsequent requests"
([#protocol-version-header](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#protocol-version-header)) —
i.e., after the initialize handshake; servers SHOULD assume `2025-03-26` if it's missing,
and MUST reject an invalid/unsupported version with 400.

**Origin validation & local binding (all revisions since 2024-11-05).** "Servers **MUST**
validate the `Origin` header on all incoming connections to prevent DNS rebinding
attacks"; servers "SHOULD bind only to localhost (127.0.0.1)"; servers "SHOULD implement
proper authentication for all connections." 2025-11-25 adds the required status: an
invalid `Origin` MUST be answered with **HTTP 403 Forbidden** ([changelog minor change #3](https://modelcontextprotocol.io/specification/2025-11-25/changelog)).

**Ping ([utilities/ping](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/ping)).**
Optional both directions: "Either the client or server can initiate a ping"; the only
MUST is that the receiver "MUST respond promptly with an empty response." Senders MAY
treat ping timeouts as stale/fatal. No default interval is specified anywhere.

### 1.2 Current shape (2026-07-28) — the stateless rewrite

Normative page: [2026-07-28 basic/transports/streamable-http](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http). Opening notice, verbatim:

> "Revision 2026-07-28 changed the behavior of Streamable HTTP. Clients must ensure they
> handle backwards compatibility correctly. Changes included: Removal of the GET stream
> endpoint. Removal of protocol-level sessions."

([changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog))

- **POST-only endpoint**: "The server **MUST** provide a single HTTP endpoint path … that
  supports POST." The client **MUST NOT** send JSON-RPC responses (client-callback
  flows are handled differently now).
- **No sessions**: servers receiving legacy-style `Mcp-Session-Id` headers SHOULD "ignore
  it, and do not mint or echo session IDs"; GET or DELETE to the endpoint gets **405**.
- **No resumability**: "A broken response stream loses the in-flight request; clients
  **MUST** re-issue it as a new request with a new request ID (SEP-2575)." `Last-Event-ID`
  is simply ignored.
- **No `ping`** (major change #5; also removes `logging/setLevel` and
  `notifications/roots/list_changed` — log level moves into request `_meta`).
- **Per-request versioning**: every POST MUST carry `MCP-Protocol-Version`, whose value
  MUST match `io.modelcontextprotocol/protocolVersion` in the body's `_meta`; mismatch →
  400 with JSON-RPC `HeaderMismatch` (code -32020); unsupported version → 400 with
  `UnsupportedProtocolVersionError` (-32022). "There is no negotiation handshake"
  ([basic/versioning](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning));
  servers MUST implement `server/discover` to advertise capabilities.
- **New required routing headers** (SEP-2243): `Mcp-Method` on all requests and
  `Mcp-Name` on `tools/call`, `resources/read`, `prompts/get` — "These headers are
  **REQUIRED** for compliance," with `x-mcp-header`-annotated tool parameters mirrored
  to `Mcp-Param-{Name}` headers.
- **Subscriptions replace GET streams**: server-initiated notifications arrive only via
  an explicit `subscriptions/listen` request whose response is itself an SSE stream
  ([basic/patterns/subscriptions](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/subscriptions.md));
  "Closing the SSE response stream **MUST** be treated by the server as cancellation of
  that request." Servers SHOULD send `X-Accel-Buffering: no` on SSE responses and are
  encouraged to emit SSE comment lines (`:\r\n`) as keep-alives — this is the only
  keepalive guidance left in the current spec.
- **Compat probing**: a client POSTs a modern-shaped request; a 4xx with an empty or
  unrecognized body ⇒ fall back to the legacy `initialize` handshake (and possibly
  further back to deprecated HTTP+SSE); a recognized modern JSON-RPC error body means the
  server is modern.

Practical read: **"legacy" (`2025-11-25` and earlier, initialize + session ids) is the
compatibility target for the foreseeable future** — SDK 1.x, most deployed servers, and
most clients still speak it — while 2026-07-28 defines where the protocol is going
(stateless, connection-less, one-POST-per-request, well-suited to per-run ephemeral
clients).

### 1.3 HTTP+SSE (2024-11-05) — deprecated origin

[2024-11-05 transports](https://modelcontextprotocol.io/specification/2024-11-05/basic/transports#http-with-sse):
two endpoints — a GET SSE stream plus a POST endpoint revealed by a server-sent
`endpoint` event. Deprecated since `2025-03-26` ("Streamable HTTP was introduced in
protocol version 2025-03-26 as a replacement for the HTTP+SSE transport from protocol
version 2024-11-05"), classified Deprecated under SEP-2596, eligible for removal in a
future revision. New clients need it only if they want to talk to very old servers.

---

## 2. Authorization

Primary pages: [2026-07-28 authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
(+ sub-pages [authorization-server-discovery](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/authorization-server-discovery.md),
[client-registration](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/client-registration.md),
[security-considerations](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations.md)),
[2025-11-25 authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization.md),
SEP index ([modelcontextprotocol.io/seps/index.md](https://modelcontextprotocol.io/seps/index.md)),
and the extensions repo [modelcontextprotocol/ext-auth](https://github.com/modelcontextprotocol/ext-auth).

### 2.1 What is mandated vs permitted

The gate, verbatim (identical across 2025-03-26 → draft):

> "Authorization is **OPTIONAL** for MCP implementations. When supported:
> * Implementations using an HTTP-based transport **SHOULD** conform to this specification.
> * Implementations using an STDIO transport **SHOULD NOT** follow this specification, and
>   instead retrieve credentials from the environment."

- **No production/remote qualifier exists** — searched the spec repo; the claim
  "OAuth required for production deployments" is folklore. The condition is only
  HTTP-vs-stdio.
- **Only the *authorization server* is OAuth-mandated**: "Authorization servers **MUST**
  implement OAuth 2.1…" The MCP server is cast purely as an OAuth **resource server**;
  "The implementation details of the authorization server are beyond the scope of this
  specification." (The 2025-03-26 text had the MCP server itself acting as the OAuth AS;
  the 2025-06-18 revision removed that.)
- **Is a plain bearer/API-key header compliant?** There is no "custom authorization
  scheme" provision anywhere in the spec. Non-OAuth auth is therefore *permitted by
  silence* (authorization is optional) but is **outside the conformant mechanism**: a
  client running the spec'd discovery flow against an API-key-only server just gets 401s
  with nothing to discover. The spec's only sanctioned non-OAuth credential channel is a
  stdio process reading env vars. The [security best-practices tutorial](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices.md)
  (recommendation, not spec) does suggest local HTTP servers "Require an authorization
  token" — it does not say which shape.
- **When OAuth is in play**, clients MUST send `Authorization: Bearer <token>` on every
  request; tokens MUST NOT appear in query strings; servers MUST return 401 for
  invalid/expired tokens (per OAuth 2.1 §5.3 error handling), 400 for malformed
  requests, and 403 + `WWW-Authenticate: Bearer error="insufficient_scope"` for scope
  failures (step-up reauthorization).
- **Token passthrough is forbidden**: servers "MUST NOT accept or transit any other
  tokens" than ones issued for them, and MUST validate the audience (RFC 8707).

### 2.2 OAuth 2.1 mechanics (2026-07-28 state)

- **Discovery**: servers MUST implement Protected Resource Metadata (RFC 9728) at
  `/.well-known/oauth-protected-resource[/<path>]` (document MUST include
  `authorization_servers`); since 2025-11-25 (SEP-985) the 401 `WWW-Authenticate` header
  is one of two equally acceptable discovery mechanisms ("MCP clients **MUST** support
  both…"). AS discovery: RFC 8414 **or** OIDC Discovery (added 2025-11-25); clients MUST
  support both; issuers with paths have a defined priority order; the `issuer` value
  MUST match the well-known URL exactly.
- **Client registration**: three mechanisms in priority order — pre-registration, Client
  ID Metadata Documents (CIMD, SEP-991, new-for-2025-11-25), or Dynamic Client
  Registration (RFC 7591). **DCR is deprecated in 2026-07-28** in favor of CIMD (MCP
  clients and ASs MAY still support it); CIMD asks ASs to fetch the client's published
  metadata document and validate `client_id` == URL and redirect URIs against it.
  `private_key_jwt` client auth is a MAY (under CIMD §6.2).
- **PKCE**: clients MUST implement PKCE (OAuth 2.1 §7.5.2) with `S256` and MUST refuse
  to proceed against an AS that does not advertise `code_challenge_methods_supported`.
- **Resource indicators**: clients MUST include RFC 8707's `resource` parameter on both
  authorization and token requests, set to the canonical MCP server URI, "regardless of
  whether authorization servers support it."
- **Redirect/transport security**: all AS endpoints over HTTPS; redirect URIs must be
  loopback or HTTPS; exact redirect-URI matching; RFC 9207 `iss` validation is a client
  MUST in 2026-07-28 (SEP-2468); client credentials MUST be keyed by AS issuer (SEP-2352);
  public clients get mandatory refresh-token rotation.

### 2.3 SEP attributions (with corrections)

- SEP-985/SEP-991/SEP-835 → 2025-11-25 (WWW-Authenticate optional / CIMD / step-up scopes)
  — [2025-11-25 changelog](https://modelcontextprotocol.io/specification/2025-11-25/changelog).
- PR #2858 (DCR deprecated), SEP-2468 (`iss`), SEP-837 (`application_type`), SEP-2352
  (credential binding), SEP-2207 (refresh tokens) → 2026-07-28 —
  [2026-07-28 changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog).
- **Correction: SEP-990 is *not* "resource-server-only mode".** Its real title is
  "Enable enterprise IdP policy controls during MCP OAuth flows" (ID-JAG; Final;
  [SEP-990](https://modelcontextprotocol.io/seps/990); landed as the Enterprise-Managed
  Authorization extension in `modelcontextprotocol/ext-auth`). The "MCP server = resource
  server, AS out of scope" reframing happened in the **2025-06-18 revision text** with no
  SEP number attached.
- **Correction: SEP-844 does not exist** in the SEP index or anywhere in the org —
  "client assertions" as a named deliverable cannot be cited; the `private_key_jwt` MAY
  is the only such text.

For **AgentGraphStudio**: a tool node configured with `{url, headers: {"Authorization":
"Bearer …"}}` toward a non-OAuth server is outside the authorization spec but is exactly
what every SDK's "custom headers" path exists for; toward an OAuth server, the
`mcp` SDK's OAuth providers / FastMCP `BearerAuth`/`OAuth` plug in via `httpx.Auth`.

---

## 3. Official Python SDK (`modelcontextprotocol/python-sdk`, PyPI `mcp`)

Sources: repo at tag `v1.30.0` and `v2.3.0` (file paths below pin the tag);
[py.sdk.modelcontextprotocol.io](https://py.sdk.modelcontextprotocol.io/) is the official docs
site (v2 "current stable"; v1 has its own tree).

### 3.1 Two release lines — pick deliberately

- **1.x** (last: `[v1.30.0]`, 2026-09-07): the classic API, camelCase wire models in
  `mcp.types`, `httpx` 0.27+, `streamablehttp_client` factory, 3-tuple transport yield.
  Its `streamablehttp_client` (underscore) spelling is now a deprecated alias of
  `streamable_http_client`.
- **2.x** (current: `[v2.3.0]`, 2026-10-02): breaking rewrite aligned to the 2026 wire —
  deps `httpx2>=2.10.0` and a split `mcp-types` package pinned to the same version,
  snake_case field names (camelCase JSON aliases preserved), a new high-level
  `Client`, `server/discover` probing (`Client(mode="auto")`, `MODERN_PROTOCOL_VERSIONS =
  ("2026-07-28",)`), and `MCPError` replacing `McpError` (`mcp/shared/exceptions.py`).

Everything below cites 1.x paths (the ecosystem's lingua franca) with 2.x deltas noted.

### 3.2 Connection API and defaults — `streamable_http_client` / `StreamableHTTPTransport`

`[v1.30.0/src/mcp/client/streamable_http.py]`:

```python
@asynccontextmanager
@deprecated("Use `streamable_http_client` instead.")
async def streamablehttp_client(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float | timedelta = 30,
    sse_read_timeout: float | timedelta = 60 * 5,   # 300 s
    terminate_on_close: bool = True,
    httpx_client_factory: McpHttpClientFactory = create_mcp_http_client,
    auth: httpx.Auth | None = None,
)
```

The **non-deprecated** 1.x factory is `streamable_http_client(url, *, http_client:
httpx.AsyncClient | None = None, terminate_on_close: bool = True)`; its transport takes
only `url` — "Parameters headers, timeout, sse_read_timeout, and auth are deprecated.
Configure these on the httpx.AsyncClient instead" (runtime `DeprecationWarning` if
passed; they are ignored). In 2.x the transport is `StreamableHttpTransport(url, *,
max_sse_event_size=1 MiB)` and the factory also accepts `http_client: httpx2.AsyncClient`
with the docstring "To configure headers, authentication, or other HTTP settings, create
an httpx2.AsyncClient and pass it here."

**Default timeouts** ([v1.30.0/src/mcp/shared/_httpx_utils.py](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/src/mcp/shared/_httpx_utils.py)):

```python
MCP_DEFAULT_TIMEOUT = 30.0            # connect / write / pool
MCP_DEFAULT_SSE_READ_TIMEOUT = 300.0  # read - because "a server may hold a response
                                      # stream open"
timeout = httpx.Timeout(MCP_DEFAULT_TIMEOUT, read=MCP_DEFAULT_SSE_READ_TIMEOUT)
```

`terminate_on_close=True` sends the HTTP DELETE session-termination at context exit when
a session id exists (405 → "Server does not allow session termination" is tolerated).
Redirects are followed **only within the endpoint's origin**.

### 3.3 Custom headers and auth

Headers are rebuilt per request in `_prepare_headers()` and merged over the
`httpx.AsyncClient` defaults, with MCP-specific values taking precedence:
`accept: application/json, text/event-stream`, `content-type`, `mcp-session-id` (when
assigned), `mcp-protocol-version` (when negotiated). Consequently:

- **Auth/API-key headers go on the httpx client**: `http_client=httpx.AsyncClient(
  headers={"Authorization": "Bearer <token>"}, auth=SomeHttpxAuth())` passed to
  `streamable_http_client(...)` is the supported 1.x path; the legacy
  `streamablehttp_client(headers=..., auth=...)` still works but warns.
- **Any `httpx.Auth` subclass is accepted** (`create_mcp_http_client(..., auth=...)`,
  the OAuth client providers are `httpx.Auth` subclasses; 2.x `RedirectAwareAuth(ABC,
  httpx2.Auth)`).
- 2.x adds **per-request** headers via `ClientMessageMetadata.headers` (how the session
  stamps `mcp-protocol-version`, and how `x-mcp-header`-annotated tool parameters become
  `Mcp-Param-*` headers on 2026-07-28 connections).

### 3.4 `ClientSession`, the handshake, and what the factory yields

`[v1.30.0/src/mcp/client/session.py]`:

```python
ClientSession(
    read_stream, write_stream,
    read_timeout_seconds: timedelta | None = None,   # client-side request timeout
    sampling_callback=..., elicitation_callback=..., list_roots_callback=...,
    logging_callback=..., message_handler=..., client_info: Implementation | None = None,
)
```

`async with streamable_http_client(url) as (read, write, get_session_id)` — exactly a
3-tuple of `MemoryObjectReceiveStream`, `MemoryObjectSendStream`, and
`GetSessionIdCallback` (`transport.get_session_id`, returns `str | None`). **2.x yields
only 2 values** (`TransportStreams = tuple[ReadStream, WriteStream]`) — no session-id
callback, mirroring the spec's removal of sessions.

`await session.initialize()` sends `InitializeRequest{protocolVersion:
LATEST_PROTOCOL_VERSION, clientInfo: "mcp"}`; raises `RuntimeError` if the server's
counter-offer is unsupported; stores `result.capabilities` (`get_server_capabilities()`)
and returns **`InitializeResult(protocolVersion, capabilities, serverInfo,
instructions)`**. The transport then echoes the negotiated version (`mcp-protocol-version`)
and the session id on every subsequent HTTP request — exactly the 2025-11-25 spec MUSTs.

### 3.5 `list_tools` and the `Tool` model

`list_tools(cursor=None)` returns **`ListToolsResult(tools: list[Tool], nextCursor:
str | None)`** ("An opaque token representing the pagination position after the last
returned result"). `[v1.30.0] mcp.types.Tool` (`src/mcp/types.py` L1315–1339):

| Field | Type | Notes |
|---|---|---|
| `name` | `str` | from `BaseMetadata` |
| `title` | `str \| None` | "for Tool, `annotations.title` should be given precedence over using `name`, if present" |
| `description` | `str \| None` | |
| `inputSchema` | `dict[str, Any]` | JSON Schema object |
| `outputSchema` | `dict[str, Any] \| None` | |
| `icons` | `list[Icon] \| None` | |
| `annotations` | `ToolAnnotations \| None` | `title`, `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` — all `bool \| None`; "Clients should never make tool use decisions based on ToolAnnotations received from untrusted servers" |
| `_meta` | `dict[str, Any] \| None` | |
| `execution` | `ToolExecution \| None` | SEP-1686 tasks (removed on the 2026-07-28 wire) |

2.x moves this into `mcp-types` with snake_case names (`input_schema`, …) and aliases.

### 3.6 `call_tool` and `CallToolResult`

```python
async def call_tool(
    self,
    name: str,
    arguments: dict[str, Any] | None = None,
    read_timeout_seconds: timedelta | None = None,   # per-call client-side timeout
    progress_callback: ProgressFnT | None = None,
    *,
    meta: dict[str, Any] | None = None,
) -> types.CallToolResult
```

Return type (`[v1.30.0] types.py L1363–1369`): **`CallToolResult(content:
list[ContentBlock], structuredContent: dict[str, Any] | None,
isError: bool = False)`** (every result also carries `_meta`).
`ContentBlock = TextContent | ImageContent | AudioContent | ResourceLink |
EmbeddedResource` — `TextContent{type:"text", text}`, `ImageContent`/`AudioContent`
(base64 `data` + `mimeType`), `ResourceLink`, `EmbeddedResource{type:"resource",
resource: TextResourceContents | BlobResourceContents}`.

**Error semantics (normative split, from the session docstring):** "Errors that originate
from the tool SHOULD be reported inside the result with `is_error` set to true, not as an
MCP protocol-level error… Errors in finding the tool … should be reported as an MCP
error response." Concretely:

- Tool execution failure → returned `CallToolResult(isError=True)`; **`call_tool` does
  not raise**.
- Unknown tool / protocol problems → `McpError(error: ErrorData(code, message, data))`
  raised by `send_request` on `JSONRPCError`.
- `structuredContent` that fails the tool's declared `outputSchema` → `RuntimeError`
  (`_validate_tool_result`).
- Client-side wait exceeding `read_timeout_seconds` (session default 30 s? no —
  `None` = no client-side timeout in 1.x; the HTTP read timeout is the 300 s
  httpx one) → `anyio.fail_after` converts `TimeoutError` to
  `McpError(code=408 REQUEST_TIMEOUT, message="Timed out while waiting for response…")`
  ([send_request](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/src/mcp/shared/session.py)).

### 3.7 HTTP status handling, session loss, exceptions

- **1.x**: the POST handler calls `response.raise_for_status()`, so any non-2xx becomes
  an `httpx.HTTPStatusError`. Because the HTTP work runs as a task in the transport's
  `anyio` task group, these — along with `httpx.ConnectError` on connection failure —
  surface to the caller **wrapped in an ExceptionGroup** (`BaseExceptionGroup`) at the
  point the first session call awaits or the context manager exits. *Inferred from source
  structure (`tg.start_soon(handle_request_async)`), not executed; this is also the
  long-reported behavior of this SDK.*
- **2.x**: no `raise_for_status` on the request path; non-2xx is synthesized into a
  JSON-RPC error on the read stream → surfaces as **`MCPError`**: body-decoded JSON-RPC
  error wins ("A spec-correct server may return the JSON-RPC error in the body at a
  non-2xx status"); 404 with no session → `METHOD_NOT_FOUND "Not Found"` ("'Session
  terminated' would be a lie here"); 404 **with** a session →
  `INVALID_REQUEST "Session terminated"`; other statuses → `INTERNAL_ERROR`; a `202
  Accepted` to a request resolves with a synthesized `INVALID_REQUEST` error.
- **Session loss: no auto-reinitialize in either line.** 1.x maps 404 to a
  `JSONRPCError{code: 32600, message: "Session terminated"}` (`_send_session_terminated_error`,
  L528–540). Neither line re-runs `initialize()` for you, despite the spec's
  "client **MUST** start a new session" — callers must catch and rebuild the session
  (for a per-run client, simply create a fresh connection).
- **SSE reconnection**: both lines auto-reconnect request SSE streams honoring
  `Last-Event-ID` and the server's `retry` field, with
  `DEFAULT_RECONNECTION_DELAY_MS = 1000`, `MAX_RECONNECTION_ATTEMPTS = 2`; exhausted
  attempts resolve the request with a synthesized error ("SSE stream ended and
  reconnection attempts were exhausted"). GET-stream failures are logged/retried and never
  abort the session.

### 3.8 Keepalive

**There is no automatic ping/heartbeat in the client or transport** — repo-wide greps for
`ping_interval|heartbeat|keepalive` find nothing client-side configurable. Server pings
are answered automatically with an empty result; `await session.send_ping()` exists for
manual liveness checks. Application-level heartbeating is DIY.

---

## 4. FastMCP client

Sources: source at
[PrefectHQ/fastmcp](https://github.com/PrefectHQ/fastmcp) (`jlowin/fastmcp` 301-redirects
there; package source `fastmcp_slim/fastmcp/`), canonical docs
[gofastmcp.com](https://gofastmcp.com) (v2/v3 trees archived under /v2, /v3), PyPI.

### 4.1 Version reality

Current release **4.1.0 (2026-10-08)**; 3.x (3.0.0 shipped 2026-02-18, maintenance at
3.4.8) and 2.x (last 2.14.7, 2026-04-13) precede it. 2.x wraps official SDK v1 — so the
premise "FastMCP 2.x is effectively a superset [to target]" is stale: **4.x is the
superset, and it wraps SDK v2** ("Code constructing MCP protocol models directly 'must
also use snake_case Python field names with SDK v2'") while negotiating protocol eras
(`Client(mode="auto")` probes `server/discover` for 2026-07-28 and falls back to the
`initialize` handshake; `mode="legacy"` forces the handshake).

### 4.2 `Client` vs raw `ClientSession`

`Client` is a wrapper, not a subclass: "The Client class is responsible for MCP protocol
logic, while the Transport handles connection establishment and management", and every
transport's `connect_session()` yields a genuine `mcp.ClientSession`.
[clients/client](https://gofastmcp.com/clients/client): "All client operations require
using the `async with` context manager" — and it's **reentrant** ("multiple concurrent
`async with client:` blocks … reference counting and background session management").
Convenience methods live on Client: `list_tools()` / `list_tools_mcp()`,
`call_tool()` / `call_tool_mcp()`, `ping()`, etc.

**`call_tool` (4.x)**:

```python
call_tool(name, arguments=None, *, version=None, timeout=None,
          progress_handler=None, raise_on_error=True, meta=None)
```

Returns FastMCP's dataclass — **not** the raw SDK object and **not** a bare content list:

```python
@dataclass
class CallToolResult:
    content: list[mcp_types.ContentBlock]
    structured_content: dict[str, Any] | None
    meta: dict[str, Any] | None
    data: Any = None          # "Fully hydrated Python objects… FastMCP exclusive"
    is_error: bool = False
```

([clients/tools](https://gofastmcp.com/clients/tools)) With
`raise_on_error=True` (default) a failed tool raises **`ToolError`**
(`fastmcp.exceptions.ToolError`, message = first TextContent); with
`raise_on_error=False` you inspect `result.is_error`. Raw wire access is
**`call_tool_mcp()`** ("returns the raw CallToolResult object… It does not raise an
exception if the tool call results in an error") — introduced in 2.10.0 together with
`raise_on_error`. **Correction: a `_return_call_tool_result` parameter does not exist**
in any release checked (2.8.0 → 4.1.0).

### 4.3 Streamable HTTP transport

`[fastmcp_slim/fastmcp/client/transports/http.py]`:

```python
StreamableHttpTransport(
    url: str | AnyUrl,
    headers: dict[str, str] | None = None,
    auth: httpx2.Auth | Literal["oauth"] | str | None = None,
    httpx_client_factory: McpHttpClientFactory | None = None,
    verify: ssl.SSLContext | bool | str | None = None,
)
```

There are **no `timeout`, `sse_read_timeout`, or `terminate_on_close` parameters** in
4.x (`terminate_on_close` never existed on FastMCP transports; `sse_read_timeout` was a
deprecated no-op by 2.14.7 and exists only on `SSETransport` now). **URL inference**:
"they are assumed to be Streamable HTTP URLs unless they end in `/sse`"
([clients/transports](https://gofastmcp.com/clients/transports)); rule is
`re.search(r"/sse(/|\?|&|$)", path)` in `mcp_config.infer_transport_type_from_url`.
Config dicts use a top-level `mcpServers` key with per-server `url`, `transport:
"http" | "streamable-http" | "sse" | "stdio"`, `headers`, `auth`.

### 4.4 Auth

- **`BearerAuth`** is a 20-line `httpx.Auth` subclass that sets
  `Authorization: Bearer <token>` ([client/auth/bearer.py](https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/auth/bearer.py)).
- **String shortcut**: `Client(url, auth="<token>")` → `BearerAuth(token)`; "do not
  include the `Bearer` prefix. FastMCP will add it for you"
  ([clients/auth/bearer](https://gofastmcp.com/clients/auth/bearer), feature added 2.6.0).
- **Plain headers**: `headers={"X-API-Key": ...}` for non-Bearer schemes.
- **Arbitrary `httpx.Auth` passthrough**: yes (`_set_auth` stores any auth object as-is);
  special-cased `OAuth` (browser flow, `auth="oauth"`) and 4.x
  `ClientCredentialsOAuthProvider` / `PrivateKeyJWTOAuthProvider`.
- **Correction: `http_auth` never existed** on `Client`/transports in any tag checked
  (2.3.0–4.1.0); the parameter has been `auth` since 2.6.0.

### 4.5 Tool metadata

`client.list_tools()` returns plain SDK `Tool` objects (`list[mcp_types.Tool]`), auto-
paginated in 4.x (`max_pages=250`). **There is no FastMCP client-side `Tool` subclass and
no `tags`/`enabled` attributes on it.** Server-side FastMCP components inject tags under
a `_meta` namespace: `tool.meta["fastmcp"]["tags"]` (4.x) / `meta["_fastmcp"]["tags"]`
(2.x, with `include_fastmcp_meta` server setting)
([components.py](https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/utilities/components.py)).
A disabled tool (`mcp.disable()`) **disappears from `tools/list`** rather than appearing
flagged ("A disabled tool disappears from listings and cannot be called"). **SEP-1865
UI-visibility hints: unconfirmed in FastMCP** — no trace in docs/source checked.

### 4.6 Timeouts and connection lifetime

- Defaults inherit the official SDK's (`httpx2.Timeout(30, read=300)`); `Client(timeout=…)`
  becomes the session `read_timeout_seconds`; per-request `timeout=` on `call_tool`;
  `Client(init_timeout=…)` for the handshake ("Failed to initialize server session"
  `RuntimeError` on expiry).
- **One connection per `async with` block, reused for every call inside it** — the same
  `ClientSession` serves all sequential `list_tools`/`call_tool`s; `client.new()`
  fabricates an independent session; stdio transports have a `keep_alive=True` subprocess
  reuse (HTTP has no analog).
- **No auto-reconnect**: session death re-raises the background task's exception
  (normalized to `RuntimeError("Client failed to connect: …")` / `"Server session was
  closed unexpectedly"`). Resilience = leave and re-enter the context manager.

### 4.7 Which library to target

- **FastMCP 4.x** (wraps SDK 2.x): most ergonomic client (`ToolError`, hydration, auth
  helpers, era negotiation, pagination), fastest-moving, Prefect-backed — but adds a
  dependency and its own layer of churn (2 → 3 → 4 API resets visible in the docs trees).
- **Official `mcp` SDK directly**: 1.x line if you want what the ecosystem/frameworks
  (langchain-mcp-adapters et al.) still bind to and camelCase types; 2.x line if you
  want the foundation library (snake_case, `mcp-types`, `httpx2`, era auto-negotiation)
  with fewer opinions.
- Raw facts for the comparison: FastMCP exists *only* because it wraps the official SDK
  (`from mcp import ClientSession` sits at the top of its client module); its value-add
  is ergonomics (this §4), not capability — everything FastMCP does is expressible in
  `mcp` SDK + ~100 lines of glue. The inverse is not true (OAuth client flow, era
  negotiation are nontrivial glue).

---

## 5. Per-run connection in practice

(For AgentGraphStudio's BackgroundRunWorker model; facts + what is *not* documented.)

- **Setup cost.** Legacy Streamable HTTP: TCP(+TLS) connect → POST `initialize` → POST
  `notifications/initialized` (the last is a `202 Accepted`). That is the documented
  protocol cost; **no primary source publishes a wall-clock figure**, and any per-run
  budget has to be derived empirically (e.g. local LAN ~tens of ms; public HTTPS a few
  hundred ms dominated by TLS) — flagged as unconfirmed. Compare stdio spawn: a new OS
  process, env bootstrap, and process-protocol handshake per run. Modern (2026-07-28)
  servers eliminate the handshake entirely: a fresh connection is just a POST on a new
  httpx client.
- **Reuse across sequential `tools/call`s.** Yes, by construction: while the transport
  context is open, every call_tool is an independent POST over the *same* pooled
  httpx client / open session (section 3.2, 4.6). There is no per-call session creation
  in the official SDK, ever — "new session per tool call" is a *framework* choice
  (langchain-mcp-adapters default, LlamaIndex), not an SDK or spec one.
- **Keepalive/health.** Spec: `ping` request/response is optional; receiver MUST answer;
  no default interval (2025-x) — and ping is **removed** on the 2026 wire, replaced by
  SSE comment-line keep-alives that servers are *encouraged* (SHOULD-level, not MUST) to
  emit. SDK: no pings are ever sent automatically; only the read timeout (300 s) will
  surface a hung connection. If an agent run can idle mid-run, an app-level
  `session.send_ping()` cadence must be built by the caller.
- **Disconnect / stream interruption.** Legacy: request SSE streams auto-reconnect
  (~2 attempts, 1 s delay, honoring `retry`) with `Last-Event-ID` redelivery scoped to
  that stream; the client never redelivers other streams' messages. If the TCP
  connection under an idle GET stream dies it is retried invisibly. Modern: a broken
  response stream loses the in-flight request; the client MUST re-issue it with a new
  request id (SEP-2575).
- **Stale session (`Mcp-Session-Id` expired).** HTTP **404**, not a distinct status;
  spec makes 404-on-session the canonical "session ended" signal and REQUIRES the client
  to re-initialize. SDK: 1.x raises `JSONRPCError(32600, "Session terminated")` / 2.x
  `MCPError(INVALID_REQUEST, "Session terminated")` — **and does not re-initialize for
  you**. Per-run clients sidestep the issue: a run that opens its own connection gets a
  fresh session (or 404-free stateless modern behavior) and nothing to expire.
- **Shutdown.** `terminate_on_close=True` (default) fires the DELETE on context exit;
  servers that disallow client termination answer 405 and the SDK proceeds anyway. On
  the modern wire DELETE is simply 405'd and there is nothing to clean up.
- **Implication held with the facts above:** for a per-run worker, open one connection
  at run start, `list_tools()` once (or cache per-run), make sequential `call_tool`s
  over the same session, and close the context at run end. The per-run overhead is
  bounded by TCP+TLS+one-or-two POSTs on legacy servers and one POST on modern ones;
  re-connection on mid-run failure is "catch the session-terminated error (or run
  FastMCP's reconnect-less `async with` again) and re-issue."

---

## Corrections and unconfirmed items (explicit)

Assumed in the ticket/older material but **not true** or **unverifiable**:

1. `SEP-990` ≠ resource-server-only mode (it's enterprise IdP / ID-JAG). ✓ corrected above
2. `SEP-844` (client assertions) does not exist in the SEP index or org repos. ✓
3. "Authorization required for production/remote deployments": no such spec text. ✓
4. "Custom authorization schemes" provision: does not exist; non-OAuth auth is
   spec-*tolerated* via "Authorization is OPTIONAL", not endorsed. ✓
5. FastMCP `http_auth` / `_return_call_tool_result`: never existed. ✓
6. FastMCP client-side `Tool` with `tags`/`enabled` attributes: does not exist (tags live
   in `_meta`, enabled = omission from `tools/list`). ✓
7. "Open/CLOSED SSE stream" control: not MCP spec vocabulary in any revision checked. ✓
8. **Inferred, not executed**: ExceptionGroup wrapping in SDK 1.x (task-group structure)
   and exact surfacing point of connection failures; DELETE success status (200 vs 204)
   is unspecified in the spec.
9. 2.x `server/discover` wire details verified only from SDK source, not from a spec page
   fetched during research; the 2026-07-28 spec pages do exist and were verified
   separately (Summary point 1).
10. `modelcontextprotocol.info` is a third-party mirror — not used as a source of any
    normative claim.
11. `mcp` 1.x-vs-2.x per-release changelogs were not exhaustively read (version dates are
    PyPI upload timestamps).
12. FastMCP `main`-branch files cited may be slightly ahead of tag `v4.1.0` (research
    pulled on 2026-10-11).

---

## Sources

- Spec (current): [2026-07-28 transports/streamable-http](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) · [versioning](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning) · [subscriptions](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/subscriptions.md) · [changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog) · [deprecated](https://modelcontextprotocol.io/specification/2026-07-28/deprecated)
- Spec (legacy): [2025-11-25 transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) · [ping](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/ping) · [2025-11-25 changelog](https://modelcontextprotocol.io/specification/2025-11-25/changelog) · [2025-06-18 transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports) · [2024-11-05 transports (HTTP+SSE)](https://modelcontextprotocol.io/specification/2024-11-05/basic/transports#http-with-sse)
- Authorization: [2026-07-28 authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) (+ discovery / client-registration / security-considerations sub-pages) · [2025-11-25 authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization.md) · [security best practices (tutorial)](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices.md) · [SEP-990](https://modelcontextprotocol.io/seps/990) · [SEP index](https://modelcontextprotocol.io/seps/index.md) · [ext-auth repo](https://github.com/modelcontextprotocol/ext-auth)
- Official SDK: [py.sdk.modelcontextprotocol.io](https://py.sdk.modelcontextprotocol.io/) · [v1.30.0 streamable_http.py](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/src/mcp/client/streamable_http.py) · [v1.30.0 _httpx_utils.py](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/src/mcp/shared/_httpx_utils.py) · [v1.30.0 client/session.py](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/src/mcp/client/session.py) · [v1.30.0 types.py](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/src/mcp/types.py) · [v1.30.0 shared/session.py](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/src/mcp/shared/session.py) · [v2.3.0 streamable_http.py](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/client/streamable_http.py) · [v2.3.0 client/session.py](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/client/session.py) · [v2.3.0 pyproject.toml](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/pyproject.toml) · [PyPI mcp](https://pypi.org/pypi/mcp/json)
- FastMCP: [repo (PrefectHQ/fastmcp)](https://github.com/PrefectHQ/fastmcp) · [docs gofastmcp.com](https://gofastmcp.com) · [clients/client](https://gofastmcp.com/clients/client) · [clients/tools](https://gofastmcp.com/clients/tools) · [clients/transports](https://gofastmcp.com/clients/transports) · [clients/auth/bearer](https://gofastmcp.com/clients/auth/bearer) · [clients/auth/oauth](https://gofastmcp.com/clients/auth/oauth) · [whats-new](https://gofastmcp.com/getting-started/whats-new) · [client/client.py](https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/client.py) · [transports/http.py](https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/transports/http.py) · [auth/bearer.py](https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/client/auth/bearer.py) · [mcp_config.py](https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/mcp_config.py) · [PyPI fastmcp](https://pypi.org/pypi/fastmcp/json)
- Companion note: [mcp-client-integration-patterns.md](./mcp-client-integration-patterns.md)