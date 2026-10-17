# PRD: MCP client support — external MCP servers as Agent tools

Status: Draft → for hand-off to an implementation effort
Effort: [Wayfinder map #116](https://github.com/manojmanivannan/AgentGraphStudio/issues/116)
Decisions: #117, #118, #119, #120, #121, #122, #123, #125, #126, #127 (all resolved — see [Decision log](#decision-log))
Related ADR: [docs/adr/0009-mcp-client-tool-integration.md](../adr/0009-mcp-client-tool-integration.md)

---

## 1. Scope statement

Worker Agents can invoke tools hosted by **external MCP servers**, reached over
**Streamable HTTP** from the backend host process. An MCP-backed Tool Node
grants a user-selected subset of one registered server's tools to the Agent
Nodes wired to it; at run time those tools ride the existing DSPy tool-callable
seam, the same approval/HITL machinery as author tools, and the same
graceful-degradation posture as every other tool failure.

**In scope**

- Client direction only (AgentGraph calls out to MCP servers).
- Legacy Streamable HTTP revisions (2025-03-26 → 2025-11-25): `initialize`
  handshake + optional `Mcp-Session-Id`. Everything deployed today speaks this
  shape (#125, #118).
- Official `mcp` Python SDK **1.x**, pinned `mcp>=1.30,<2` (#125).
- Workspace-global server registry, per-node tool selection, live catalog
  reads, per-run sessions, per-tool approval defaults, secret redaction at the
  event boundary.

**Out of scope** (map "Out of scope" section — do not re-open here)

- MCP **server** direction (exposing canvas agents as MCP tools); A2A.
- **stdio** transport; modern **2026-07-28** protocol revision, HTTP+SSE
  fallback, compat-probe negotiation (deferred to a later effort that
  re-evaluates `mcp` 2.x from scratch).
- OAuth 2.1 client flow (deferred; plain custom-header credentials in v1).
- Implementation — this spec is the hand-off artifact.

**Non-goals that are explicit design decisions** (decided, not open):

- No MCP warm-connection pool; no catalog cache anywhere (#126, #127).
- No auto-prefixing / silent renaming of colliding tool names (#121).
- No server-level enable/disable toggle or server-level approval policy
  (#120, #122).

---

## 2. Domain-model changes

### 2.1 New tables

**`mcp_servers`** — workspace-global registrations (multi-row table, borrowing
`provider_settings` conventions: process-local cache, refresh on `PUT`,
`*_set` redaction — not the singleton-row pattern). Per #120:

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `name` | String(255) | display name, unique enough for pickers |
| `url` | String(2083) | endpoint; validated `http(s)://` (#122 §1) |
| `credential_header` | String(64), nullable | header name, default `Authorization` |
| `credential_value` | Text, nullable | header value (e.g. `Bearer sk-…`); DB-only |

**`tool_nodes`** gains columns (migration; no new node type — decision #119):

| column | type | notes |
|---|---|---|
| `mcp_server_id` | UUID FK → `mcp_servers.id`, nullable | non-null ⇒ MCP-backed node; `code` stays empty |
| `mcp_tools` | JSON, default `[]` | enabled-tools list: `[{name, requires_approval}]` — per-tool approval granularity (#119 Q9) |

- The existing node-level `requires_approval` boolean continues to govern
  author (code) tools only. MCP approvals live per enabled tool in `mcp_tools`.
- **No schema snapshot is persisted on the node.** This resolves the open note
  on #121: the unused `args` column stays empty for MCP nodes. Tool Inspection
  derives the live schema from a probe (#126); the ZIP export embeds a
  metadata snapshot captured at export time (§2.3), and import restores it as
  reference metadata only.

### 2.2 Grant semantics (decision #119)

- **Grant unit = (server reference, enabled-tools selection).** The
  Agent→Tool Edge grants exactly that subset — never all of the server's tools.
- Two agents wanting different subsets of one server get **two nodes**; two
  agents wired to the same node share its selection.
- **No silent growth**: new tools a server starts exposing surface as
  unselected suggestions in the node's picker; they never grant themselves.
- **No silent loss**: an enabled tool the server no longer offers is excluded
  from the grant and flagged ("N of M enabled tools unavailable") — never a
  crash, never faked.
- **CONTEXT.md** glossary already updated (uncommitted on this branch):
  widened Tool Node + Tool Inspection / Tool Test / Tool Approval, new
  **MCP Tool**, **MCP Server**, **MCP Tool Catalog** terms.

### 2.3 ZIP package (decision #119)

Canvas/conversation ZIP export carries, per MCP node: the **server reference**
(resolved server name + URL if it resolves; else recorded as unresolvable) and
a **metadata snapshot** (tool names, descriptions, input schemas) taken at
export. **Never credentials.** Import re-points to an existing workspace
registration by name/URL and warns when unresolvable; nodes import as
not-yet-granting until the user confirms a registration.

---

## 3. Connection & credential management (decision #120)

### 3.1 Registry UI

A new **"MCP Servers"** section in the Settings dialog
(`components/settings/sections/`, registered in
`components/settings/registry.ts`). Multi-row management consistent with
provider-profile conventions. No per-canvas overrides.

- **Fields**: name, URL, credential header (advanced, default `Authorization`)
  and value. One custom header per server in v1 (covers bearer, API-key-in-header, basic-ish).
- **Redaction**: the credential value is never returned by `GET`; responses
  expose `credential_set` plus a masked preview. `PUT` with `null` credential
  keeps the stored one; `""` clears it.
- **Test connection**: `POST /api/mcp/servers/test` — full-parity probe
  mirroring `provider_probe.py`: connect + `initialize` + `tools/list` from the
  **backend environment** (never the sandbox), returning `ok`, and on success
  server name/version from the handshake, tool names + count, and latency (ms).
  Accepts an unsaved-form override for credential (provider Test-button
  convention). Probe responses **exclude the credential** (#122 §4).
- **Unspeaking servers** (#125): when `initialize` fails because the server
  speaks an unsupported revision, the probe classifies best-effort (e.g.
  JSON-RPC error `-32022`, POST-only/no-session-echo shapes) and reports
  *"Server speaks protocol revision ⟨X⟩; this client supports Streamable HTTP
  legacy revisions (2025-03-26 → 2025-11-25)."* Unrecognized failure shapes
  collapse to the generic connection-failure class. Run-time behavior is
  unchanged (§4.6).

### 3.2 Connection lifetime

- **Per-run sessions.** Opened during agent setup when the run's graph
  references a server; reused across all MCP tool calls in the run; closed at
  run end (§4.3). Stale `Mcp-Session-Id` (404 / "Session terminated") triggers
  **one** re-handshake mid-run; a genuine connect/TLS/auth failure does not.
  (#120, #118)
- **Benchmarked justification** (#127): full legacy handshake costs 2 ms
  (localhost) → 0.5–0.92 s p50 against distant public servers (~82–150 ms RTT,
  TLS included); hand-shake ≈ 6×RTT for non-CDN servers. With 10 tool calls in
  a run, per-tool-call connections would add +8.2 s (deepwiki) — per-run
  sessions are the difference between immaterial and user-visible. The
  #120 fallbacks (per-tool-call session / pooled long-lived session) are
  **documented fallbacks, not mechanisms**; do not exercise them.
- **Scale rule**: when a run references >2 servers with RTT ≥150 ms, open the
  per-run connections **concurrently at setup** (aggregate opens serialize to
  ≈4.5 s+ for 5 distant servers otherwise).
- **The BackgroundRunWorker is the only long-lived MCP session holder.** API
  processes hold only short-lived probe connections (§5.2). No idle-session
  management, no warm pool (#126, #127).

### 3.3 Edits & deletion

- **Edits propagate live**: referencing canvases run against the new URL /
  credential on their next run. References are the point.
- **Delete is guarded**: rejected with HTTP 409 while any Tool Node references
  the server, listing the referencing canvases in the error.
- **No enable/disable toggle on the server row** — enabling is per-tool on
  Tool Nodes; an unreferenced server is simply dormant.

---

## 4. Runtime integration (decision #121, pinned by #125/#122)

### 4.1 Integration seam — the existing tool-callable machinery

An MCP tool becomes an **async callable** carrying `__name__` / `__doc__` /
`requires_approval` / `node_id` exactly like a compiled author tool. DSPy
wrapping, approval gating (StreamingReAct HITL seam), event enrichment
(`tool_start` / `tool_result`), and graceful-failure conversion are therefore
**unchanged**. No new execution path, no new event types.

### 4.2 Descriptor pipeline

- Server `inputSchema` → `dspy.Tool.from_mcp_tool` (ships in
  `dspy/adapters/types/tool.py`). Server types are **preserved** (no coarsening
  like the AST path). Arg coercion is DSPy's pydantic lax validation at call
  time; no host-side `coerce_arg`.
- Schemas the adapter can't process fall into the existing **`failed_tool`
  stub** mechanism (raises at call time → observation), same as compile
  failures today.
- Non-DSPy-legal tool names are sanitized at descriptor build.

### 4.3 Session home — runner-local, no singleton

An MCP session registry is created in `CanvasRunner.setup()` (alongside
`_install_dependencies`) and closed in `ConversationRunCoordinator.run`'s
`finally` next to `sandbox.release_session()`. Mirrors the sandbox session
lifecycle. Sessions/key-off: **workers only**.

- **Routers get no MCP sessions.** Per architecture decision 8's rationale
  (routers never get network surfaces), session-open at setup keys off
  workers' tool grants. **Behavior change to call out**: routers currently
  *do* receive Tool Nodes via `tool_access` edges (`agent_factory.py:541-543`)
  — this spec makes router setup skip MCP-backed Tool Nodes while preserving
  their sandbox tools (surfaced by #122).

### 4.4 Timeout & concurrency

- **Per-call timeout: 60 s**, new setting in `canvas_server/config.py`
  (e.g. `mcp_tool_call_timeout_seconds: float = 60.0`). Call wrapped in
  `asyncio.wait_for`; timeout → `Execution error in <tool>: timed out after
  60s` observation; run continues. Per-server overrides: not in v1.
- **Concurrency: native, no semaphore.** `ClientSession` multiplexes by
  request id; parallel sub-agents under `asyncio.gather` share the per-run
  session concurrently. A server that mishandles concurrent requests is an
  ordinary tool failure → observation/degrade.

### 4.5 Collisions & results

- **Collisions are per-agent, first-come wins, later colliders excluded +
  flagged**: "tool `search` from server B was dropped — name already taken by a
  tool from server A". No silent merge, no failed run, **no auto-prefix**
  (LLM-visible renaming is future opt-in). The run's `tool_name → node_id`
  attribution map belongs to the first-come owner.
- **Result content**: text blocks joined into the observation; non-text blocks
  (image/audio/resource) replaced by placeholder notes (`[1 image block
  returned, 3 text blocks]`); raw content structure rides the persisted event
  payload for UI. **Size cap 50k chars** with a truncation note (this is the
  only truncation, per #122 §2).
- MCP `isError` results pass through as normal observations — call_tool never
  raises for tool errors (#118).
- **Zero new event types** — everything rides existing `tool_start` /
  `tool_result` shapes; staleness "N of M unavailable" and server-failure
  surfacing use the existing event machinery.

### 4.6 Failure posture — retry-then-degrade (decision #120)

One re-handshake on session loss mid-run (stale 404 session). On genuine
connect/TLS/auth failure, the run **continues degraded**: that server's tools
are omitted from the agents' tool lists and the failure is surfaced as an
Execution Event naming the server and reason (architecture decision 12, graceful
tool-output propagation). **The run never fails outright for one unreachable
server.** Degradation granularity stays **server-level**: if all of an agent's
tools come from one dead server, the run continues and the agent reports from
the failure observation. Per #127: connections open concurrently at setup, so
one slow server doesn't serially delay the rest.

### 4.7 Spec-mandated bug fix (from #121's survey)

`StreamingReAct.aforward` has an **unguarded `self.tools[name]` lookup** outside
the try block: an LLM-selected unknown/renamed tool name raises out of the loop
and fails the run, bypassing observation conversion. MCP makes exotic tool
names more likely. The implementation **must** guard this lookup and convert it
to the standard `Execution error in <tool>` observation.

---

## 5. Security & guardrails (decision #122)

### 5.1 URL / egress policy

- Require a valid **`http(s)://`** URL; hard-reject other schemes in Settings,
  import, and any API write path.
- **Warn (do not block) on plain `http://`** — still permitted for localhost
  dev/test servers.
- **No IP/SSRF guard, no HTTPS-forever.** Server URLs are
  workspace-operator-configured — the same self-configured posture as
  `llm_base_url`. ZIP import carries *references to existing registrations
  only*, so there is no cross-canvas URL smuggling vector.
- **Documented open egress**: MCP calls run host-side in the
  BackgroundRunWorker process — the Docker sandbox's `network_mode="none"`
  invariant does **not** apply. The Security section of the implementation and
  `docs/ARCHITECTURE.md` must state this, paralleling how architecture
  decision 8 documents the networked sandbox pool.

### 5.2 Prompt injection / untrusted results

- The **50k-char result cap** (§4.5) is the **only** truncation.
- MCP results delivered as observations are **wrapped in delimiters with an
  explicit "treat as untrusted data" framing** so injected instructions are
  delimited from the agent's own context.
- **No content filtering / instruction-pattern stripping** — rejected as
  brittle theater. Residual injection risk is documented (the MCP spec only
  *shoulds* clients into validating results; survey: zero content guards
  across mainstream frameworks, #117).

### 5.3 Tool approval

- **Mechanism unchanged**: per-enabled-tool `requires_approval` flag on the
  Tool Node, enforced at the existing StreamingReAct HITL seam (pause →
  Approve/Deny → denial recorded as the observation). No new approval path.
- **Default: `requires_approval = true` for newly enabled MCP tools** (any
  enable action, picker or editor). Human in the loop by default for opaque
  remote code + network egress. The user can switch a specific tool off. **No
  server-level policy.**
- **Enforcement guarantee**: an MCP tool requiring approval **MUST NOT run**
  when no client-response callback is wired (today's silent-skip fallback is
  not acceptable for networked tools). Implement as: unenforceable approval →
  tool excluded from the grant + event, or blocked at call time with an
  observation; silent execution is forbidden.

### 5.4 Secret redaction

- **One redaction pass at the event/error boundary** strips the configured
  credential value and the server endpoint from any error text bound for
  execution events, the UI, or MLflow. SDK/transport error strings are the
  realistic leak vector.
- **Test-probe responses exclude the credential** (§3.1).
- **No general redaction layer** — retrofitting masking across the
  observability pipeline / provider keys is separate work at the documented
  plaintext-storage trust level (ADR 0008).

---

## 6. UI spec

### 6.1 Canvas node (prototype verdict, #123)

The MCP-backed Tool Node takes the **distinct agent-purple family** (visually
distinct from code Tool Nodes) with:

- **Server icon** + server name.
- **`N tools` count badge** (enabled count).
- **Tool chips** rendering the enabled tools; chips for enabled-but-vanished
  tools render **struck-through** (#119 no-silent-loss).
- Staleness warning is **transient UI state derived from the latest run's
  events** — not persisted on the node; the next run recomputes (#126 §3).

### 6.2 Editor body — Variant A, single scrolling picker (#123 residue, decided)

One scrolling editor, no tabs (server management lives in Settings per #120;
a Server tab would duplicate it):

1. **Server chip** at top (name + endpoint) → click reopens the
   registered-servers picker (list of workspace registrations; **Manage
   servers** link → Settings dialog). Selecting a server resets the tool
   selection.
2. **Name** field.
3. **Server Tools (N) checklist**: one scrolling list with a **filter box**;
   each row = enable checkbox, tool name, truncated description,
   **approval toggle visible on enabled rows** (on-enable defaults
   `requires_approval = true`, §5.3), and **expandable schema row** (server
   schema rendered inline — this is Tool Inspection for MCP nodes, per #119).
4. **Diff badges** (per #126 §2): **NEW** badge for catalog tools not in the
   node's enablement history; enabled-but-vanished tools render in a flagged
   "Excluded — no longer on ⟨server⟩" block with a **Drop** affordance.
5. **Live fetch + Refresh**: the catalog is fetched live each picker open
   (probe path, §6.3); **Refresh** re-fetches and re-diffs. **No caching, no
   polling, no push** in v1.
6. Unreachable server → **honest error + Retry** in the picker, never stale
   data (#126 §1).

### 6.3 Catalog plumbing (decision #126)

- **No catalog cache exists anywhere** — no DB snapshot, no in-process memo.
- **Two connection paths, one client primitive**: all UI catalog reads
  (picker, refresh, editor diff) ride a **short-lived probe connection**
  (initialize + `tools/list` + close — same primitive as the #120 Test probe)
  through one shared backend endpoint (e.g. `POST /api/mcp/servers/{id}/tools`).
  Run-time `tools/list` rides the per-run session (§4.3).
- **Run-time validation only**: the run's own `tools/list` is the sole
  validation point for enablement; missing enabled tools are excluded + flagged
  (§4.5). Compile-time vs call-time collapses.

### 6.4 Inspector & Test panel (two-stage, prototype verdict)

- **Tool Inspection** (`POST /api/tools/inspect`, MCP branch): renders the
  **server-provided schema** pulled live from the probe path; the Test panel's
  argument fields build from it.
- **Test panel**: two stages —
  1. **Connection probe** (init + `tools/list` + latency — the shared
     #120/#126 path);
  2. **Live remote call** with schema-driven args, run from the **backend
     environment** (not the sandbox, #119). Call never throws: results render
     distinguishing output blocks from in-band `isError` results (per #121/
     #118). Credential: uses the stored one; Test-time override follows the
     provider convention.

---

## 7. Phased rollout

Each phase ships behind a mergeable, green `uv run pytest -v` +
`npx vitest run` (project TDD: tests written first, per layer, before
implementation).

**Phase 1 — Registry & backend foundation.** `mcp_servers` table + migration;
MCP servers CRUD routes with redaction + guarded delete (409 with referencing
canvases); Settings "MCP Servers" section; test/probe route with revision
classification; URL validation; process-local cache per provider conventions.
*Tests:* repo/routes/settings-section; redaction; probe classification.

**Phase 2 — Tool Node domain model & editor UI.** `tool_nodes` migration
(`mcp_server_id`, `mcp_tools`); save/load/serialization (repo, API, frontend
types + persistence + export/import); Variant A editor live-catalog flow
(picker, checklist, diff badges, Drop, schema expansion); canvas node badge +
chips; routes `/api/tools/inspect` + `/api/tools/test` MCP branches (probe
schema + live call from backend env); ZIP reference + metadata snapshot +
warn-on-import.
*Tests:* persistence round-trip; editor interactions; inspect/test; ZIP.

**Phase 3 — Runtime integration.** Session registry in `CanvasRunner.setup()`
→ coordinator `finally` close; concurrent connection opens; descriptor
pipeline (`from_mcp_tool` + `failed_tool` stubs + name sanitization); 60 s
timeout config + `asyncio.wait_for`; per-agent collision exclusion + flagging;
result joining/placeholder/cap; retry-then-degrade + Execution Events;
StreamingReAct unknown-tool guard (§4.7); router exclusion (§4.3).
*Tests:* worker-facing integration with a local FastMCP server
(`docs/research/mcp-handshake-benchmark.py` has a `serve-local` reference
server); collision tables; degradation; timeout; guard.

**Phase 4 — Security hardening & docs.** Approval-default on enable +
must-not-run enforcement without wired approval client; boundary redaction
pass; untrusted-data delimiter framing of observations; open-egress
documentation in `docs/ARCHITECTURE.md`; `CONTEXT.md` glossary commit
(already drafted, uncommitted); pin `mcp>=1.30,<2` in `pyproject.toml`.
*Tests:* approval enforcement guarantee; redaction pass; delimiter framing;
pin resolution.

---

## 8. Open questions

Deferred or surfaced-but-unresolved; none block implementation of the above.

1. **OAuth 2.1 client flow** — deferred beyond v1 with the modern protocol
   revision. When the 2026 adapter effort re-evaluates `mcp` 2.x, re-evaluate
   `BearerAuth`-style helpers (FastMCP 4.x) alongside.
2. **Per-server timeout overrides** — global 60 s only in v1; watch for slow
   real servers before adding a knob.
3. **Auto-prefixing as opt-in** for cross-server collisions — the exclusion +
   flag posture may annoy users with genuinely-overlapping broad servers; an
   opt-in prefix (presentation-only, stripped before `tools/call`) is the
   surveyed mainstream answer if so (#117).
4. **Elicitation & sampling requests from servers** — v1 ignores/rejects
   server-initiated requests silently; whether they should surface as HITL
   interactions is unexplored.
5. **Structured content beyond observation** — `structuredContent` rides event
   payloads raw today; a UI-side structured renderer is unscoped.
6. **Catalog polling while a picker is open** — explicitly deferred in #126 as
   a trivially addable upgrade if refresh-manual proves annoying.
7. **Credential encryption at rest** — plaintext, same documented trust level
   as provider keys (ADR 0008 follow-up), not MCP-specific work.

---

## 9. Decision log

| Decision | Ticket | Gist |
|---|---|---|
| Framework survey | [#117](https://github.com/manojmanivannan/AgentGraphStudio/issues/117) | 5-framework patterns: collisions, lifetimes, caching, guardrails. `docs/research/mcp-client-integration-patterns.md` |
| Transport & SDK facts | [#118](https://github.com/manojmanivannan/AgentGraphStudio/issues/118) | Legacy vs 2026-07-28 spec, optional auth, `mcp` 1.x/2.x split, tool-error semantics. `docs/research/mcp-streamable-http-transport.md` |
| Canvas domain model | [#119](https://github.com/manojmanivannan/AgentGraphStudio/issues/119) | (server, selection) grant on a Tool Node variant; no new node type |
| Connections & credentials | [#120](https://github.com/manojmanivannan/AgentGraphStudio/issues/120) | Settings registry, per-run sessions, retry-then-degrade, one custom header |
| Runtime integration | [#121](https://github.com/manojmanivannan/AgentGraphStudio/issues/121) | Tool-callable seam, `from_mcp_tool`, runner-local sessions, 60 s, collisions |
| Security & guardrails | [#122](https://github.com/manojmanivannan/AgentGraphStudio/issues/122) | URL policy, delimiters, approval-default true, must-not-run, narrow redaction |
| Node UX prototype | [#123](https://github.com/manojmanivannan/AgentGraphStudio/issues/123) | B's node badge + A's test panel; editor body = **A's single-scroll picker** (decided on #124) |
| Protocol target & SDK | [#125](https://github.com/manojmanivannan/AgentGraphStudio/issues/125) | Legacy-only, `mcp>=1.30,<2`, client-session interface named as the 2026 seam |
| Discovery & re-sync | [#126](https://github.com/manojmanivannan/AgentGraphStudio/issues/126) | No cache anywhere; live probe + diff; run-time-only validation |
| Handshake benchmark | [#127](https://github.com/manojmanivannan/AgentGraphStudio/issues/127) | Per-run sessions only; concurrent opens; ≈6×RTT. `docs/research/mcp-handshake-benchmark-results.md` |