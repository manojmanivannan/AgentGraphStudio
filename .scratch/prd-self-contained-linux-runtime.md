---
title: PRD - Self-contained Linux Runtime Installer
state: open
triage: ready-for-agent
category: enhancement
created: 2026-07-13
---

## Problem Statement

As an Agent Builder user, I currently need Docker Compose and multiple containers to run the product. This creates setup friction, host dependency issues, and lower portability for users who want a straightforward local install experience. The current runtime model also ties packaging and operations to container orchestration, which is not aligned with a desktop-style self-contained Distribution.

## Solution

Deliver a Linux-first Self-contained Distribution that runs Agent Builder without Docker Compose while preserving core Canvas, Conversation, Workflow, Memory, and RAG Documents behavior. The distribution will use AppImage, run bundled services under an app-owned supervisor, store runtime data in per-user directories, require KVM-capable hosts for strong tool isolation, keep MLflow optional and disabled by default, and target near parity with explicit exclusions for v1.

## User Stories

1. As a first-time Linux user, I want to download and run a single distributable artifact, so that I can start using Agent Builder without Docker Compose.
2. As a user, I want startup diagnostics before launch, so that I know whether my host meets KVM and runtime requirements.
3. As a user, I want clear failure messages when KVM is unavailable, so that I understand why tool execution cannot start securely.
4. As a user, I want my Canvas and Conversation data to persist between launches, so that my work is not lost.
5. As a user, I want all runtime data in my user space, so that I do not need root privileges for normal operation.
6. As a user, I want Worker and Router behavior to remain consistent with today, so that existing Workflows still execute as expected.
7. As a user, I want Agent Node and Tool Node definitions to load exactly as before, so that existing team assets continue to work.
8. As a user, I want Edge semantics and Handoff behavior to be preserved, so that orchestration logic does not change unexpectedly.
9. As a user, I want Memory tools to continue functioning, so that agents keep long-term context.
10. As a user, I want RAG Documents retrieval to remain available, so that domain-specific grounding continues to work.
11. As a user, I want durable run behavior to survive temporary UI disconnects, so that long runs still complete.
12. As a user, I want the Chat overlay to continue streaming Execution Events, so that I can monitor reasoning and tool use.
13. As a user, I want custom tool execution to remain strongly isolated, so that untrusted code cannot access host resources.
14. As a user, I want the app to stop all managed processes on exit, so that no orphan processes remain.
15. As a user, I want to restart the app and recover cleanly after crash or power loss, so that my runtime is resilient.
16. As a user, I want imports and exports of Canvas ZIP package and Conversation ZIP package to keep working, so that portability remains intact.
17. As a user, I want a simple way to configure external model endpoints, so that I can use my preferred inference provider.
18. As a user, I want default configuration to avoid shipping heavy local models, so that installer size is manageable.
19. As a user, I want MLflow Observability to be optional, so that default startup stays fast and lightweight.
20. As a user, I want to enable Observability only when troubleshooting, so that normal usage is simpler.
21. As a user, I want manual update instructions for AppImage releases, so that upgrades are predictable in v1.
22. As a user, I want compatibility guidance by distro family, so that I can self-serve setup issues.
23. As a user, I want compatibility with existing Conversation semantics, so that multi-turn interactions remain stable.
24. As a user, I want existing execution stop and cancellation behavior to remain intuitive, so that I trust run control.
25. As a user, I want launch-time health checks over internal services, so that failures are detected early.
26. As a maintainer, I want a private alpha channel first, so that distro-specific failures are surfaced before wider release.
27. As a maintainer, I want explicit v1 exclusions documented, so that user expectations are clear.
28. As a maintainer, I want supervisor lifecycle logs, so that support and bug diagnosis are practical.
29. As a maintainer, I want release artifacts reproducibly built in CI, so that shipping and rollback are reliable.
30. As a maintainer, I want runtime boundaries that preserve future Windows optionality, so that Linux-first delivery does not force a rewrite later.
31. As a security reviewer, I want the sandbox boundary documented and testable, so that threat model claims are verifiable.
32. As a support engineer, I want clear error classes for startup, dependency, and capability failures, so that triage is faster.
33. As a product owner, I want near parity with current capabilities in v1, so that migration value is immediate.
34. As a power user, I want confidence that default behavior does not require system-wide services, so that local control is preserved.
35. As a team lead, I want confidence that existing Workflow examples continue to run, so that onboarding assets remain valid.

## Implementation Decisions

- Runtime packaging moves to Linux-first AppImage as the primary Self-contained Distribution artifact.
- Docker Compose is removed from the runtime dependency model for this distribution path.
- Strong isolation for user-authored tool execution is mandatory for v1, with KVM host capability required.
- Runtime orchestration is owned by an application supervisor that launches and monitors internal services.
- Optional future integration with user-level service managers is allowed, but not required for v1.
- Runtime operation must not require root privileges after installation.
- One-time privileged setup is permitted only when strictly needed by host capability wiring.
- Transactional storage remains PostgreSQL in bundled local-process form for lowest behavior drift.
- Memory and vector behavior remains aligned with current mem0 plus local Qdrant semantics.
- Runtime state location is per-user data/config/cache directories, with deterministic path conventions.
- Model inference defaults to externally configured endpoints rather than bundled model weights.
- MLflow Observability is disabled by default and explicitly enabled by user choice.
- Manual update flow is accepted for v1; in-app auto-update is deferred.
- Product target for v1 is near feature parity with explicit exclusions documented in release notes.
- Release progression is private alpha to public beta to stable.
- Portability seams are maintained in process contracts and path abstractions to support future non-Linux targets.
- Existing Conversation, Turn, Execution Event, and durable run semantics are preserved as user-facing contracts.
- Existing Canvas import/export contracts are preserved for backward compatibility of user assets.

## Testing Decisions

- Good tests validate external behavior and contract outcomes rather than implementation details.
- Preferred highest seam: app-level runtime contract tests that treat the self-contained runtime as a black box and assert launch, health, execution, and shutdown behavior.
- Existing seams to reuse:
- Backend API and websocket behavior tests for run lifecycle, durable execution, and event streaming.
- Backend sandbox tests for capability and isolation behavior.
- Frontend unit and E2E tests for Canvas, Chat overlay, and execution event rendering.
- Packaging and installer smoke tests should verify first launch, restart, data persistence, and clean exit on representative Linux environments.
- Capability tests should verify required host checks (KVM availability) and user-facing diagnostics on failure.
- Regression tests should validate Canvas ZIP package and Conversation ZIP package compatibility across prior versions.
- Feature toggle tests should validate MLflow optional mode behavior without affecting core startup paths.
- Prior art: existing backend durable run, route, runner, sandbox tests and frontend Playwright suites provide baseline behavior expectations to preserve.

## Out of Scope

- Full Windows release in v1.
- In-app automatic update mechanism in v1.
- Bundled local model weights or embedded inference runtime in v1 default path.
- Runtime requiring system-wide root services for normal operation.
- Broad architectural rewrites of Worker/Router reasoning logic unrelated to packaging/runtime transition.
- Nonessential redesign of frontend UX beyond what is required for runtime diagnostics and configuration.

## Further Notes

- Domain vocabulary should remain consistent with Canvas, Agent Node, Tool Node, Edge, Handoff, Worker, Router, Workflow, Conversation, Execution Event, Memory, and RAG Documents.
- ADR baseline for this effort is already accepted and should govern implementation trade-offs.
- Any explicit v1 exclusions should be listed in release communication and linked from installer documentation.
