# 9. Remote MCP tools at the tool-callable seam

## Status

Accepted

## Context

Agent tools today are either user-written Python compiled in the Docker
sandbox or built-in DSPy tools — all defined at canvas-edit time. Exposing
tools that live on external MCP servers introduces protocol, transport,
credential, and lifetime concerns that no existing component addresses. Two
cross-cutting shapes had to be chosen before the feature could be specced:
where MCP sessions live, and how MCP tools become parts of an agent's toolset.
Surveys of five mainstream agent frameworks (#117) and the MCP
transport/SDK landscape (#118) framed the options; the decision tickets
#119–#122, #125, #126 resolved them.

## Decision

Four commitments lock the architecture:

- **Client, over legacy Streamable HTTP only, on `mcp` 1.x.** The client
  targets the 2025-03-26 → 2025-11-25 revisions (initialize handshake +
  `Mcp-Session-Id`) with the official SDK pinned `mcp>=1.30,<2` (#125). The
  2026-07-28 revision removed sessions and the handshake; supporting it is
  deferred. The client-session interface (initialize / tools-list / call,
  owned by the BackgroundRunWorker session manager) is the named seam a
  future 2026 adapter would replace — per-run ephemeral sessions happen to be
  the right shape for the stateless modern protocol too.
- **MCP tools are a variant of the Tool Node, not a new node type** (#119). A
  Tool Node either holds user-written Python or a reference: (one registered
  server, a user-selected subset of its tools). The Agent→Tool Edge grants
  exactly that subset; new server tools never auto-grant, vanished tools are
  excluded and flagged. Downstream machinery (events, approvals, ZIP,
  deletion) already keys off Tool Nodes.
- **MCP tools integrate at the existing tool-callable seam** (#121). An MCP
  tool becomes an async callable carrying `__name__`/`__doc__`/
  `requires_approval`/`node_id` like a compiled author tool; DSPy descriptors
  come from the server `inputSchema` via `dspy.Tool.from_mcp_tool`, so
  approval gating, event enrichment, and graceful-failure conversion are
  unchanged and no new event types exist.
- **Per-run sessions, runner-local, worker-only** (#120, #126, #127). Sessions
  open in `CanvasRunner.setup()` and close in the coordinator's `finally` —
  mirroring the sandbox session lifecycle — inside the BackgroundRunWorker,
  which is the only long-lived MCP session holder. The measured handshake
  cost (2 ms local, ≤ ~0.9 s p50 remote, ≈ 6×RTT; #127) makes per-run
  connection opening cheap and obviates a `SandboxManager`-style warm pool;
  UI catalog reads ride short-lived probe connections through the API
  process, never long-lived sessions there.

Routers receive no MCP tools (architecture decision 8's rationale: routers
never get network surfaces), which changes current behavior — routers today
do receive sandbox Tool Nodes.

## Consequences

- The approval/HITL, graceful-error-observation, and execution-event
  machinery generalize to remote tools for free; remote failures degrade
  instead of failing runs, consistent with architecture decision 12.
- MCP calls run **host-side in the BackgroundRunWorker** — the Docker
  sandbox's no-network invariant does not cover them. This is a documented
  open-egress posture, workspace-operator-trusted like `llm_base_url` (spec
  §5.1).
- Newly enabled MCP tools default to approval-required and **must not run**
  when no approval client is wired — tightened past today's silent skip for
  in-canvas tools (spec §5.3). Implementation choice (#140): the guarantee is
  enforced **at call time** in `StreamingReAct.aforward` (MCP-origin tools
  carrying `requires_approval` with no wired `get_client_response` are blocked
  with an observation naming the tool) rather than by excluding the tool from
  the grant — the smaller diff keeps the grant visible to the agent, and the
  existing event machinery carries the refusal with zero new event types.
  In-canvas author tools keep their pre-#140 no-callback behavior.
  MCP observations are additionally framed as untrusted data (§5.2) and a
  single redaction pass strips configured credential values + endpoint URLs
  at the event/MLflow boundaries (§5.4); see the MCP section of
  `docs/ARCHITECTURE.md` for the full security posture.
- Legacy-only pinning means modern-spec servers (already appearing in the
  wild — deepwiki/context7 speak 2026-shape, though their deployed endpoints
  still answer legacy probes) fail the Test probe with a dedicated
  classification message rather than silently misbehaving (#125).
- A future modernization effort re-evaluates `mcp` 2.x from scratch and
  replaces exactly one seam — the client-session interface.