# ADR 0007: Self-Contained Linux Runtime Without Docker Compose

## Status

Accepted

## Context

AgentGraph Studio currently runs as a Docker Compose stack. We need a self-contained Linux distribution that can be installed and run locally without Docker Compose, while preserving security for user-authored tool execution and minimizing v1 product regressions.

## Decision

Adopt a Linux-first, Docker-free runtime architecture for v1 with these constraints:

1. Require KVM-capable hosts and keep strong isolation for tool execution.
2. Ship AppImage as the primary distribution format.
3. Run services under an app-owned supervisor (with optional systemd integration later).
4. Keep PostgreSQL and current mem0 + local Qdrant behavior as bundled local services.
5. Use per-user data directories, external model endpoints by default, and manual AppImage updates for v1.
6. Keep MLflow optional and disabled by default.
7. Target near feature parity for v1 with explicit exclusions, and release via private alpha before public beta.

## Consequences

This preserves core product behavior while replacing deployment mechanics, but introduces packaging and runtime orchestration complexity. It also intentionally sets Linux-specific operational plumbing in v1 while maintaining portability seams for possible later Windows support.
