# Baked-floor sandbox image for AgentGraphStudio's Docker sandbox pools.
#
# Both the locked default pool (network_mode="none") and the lazy networked
# pool (#55) share this image — they differ only in network_mode. matplotlib +
# plotly + numpy are pre-installed so the locked pool needs NO runtime pip,
# which is impossible under network_mode="none" anyway (CLAUDE.md §8: "no
# network by default").
#
# llm-sandbox's pooled sessions execute code via the venv interpreter at
# /sandbox/.sandbox-venv/bin/python (workdir=/sandbox, venv dir=".sandbox-venv").
# We bake that venv with --system-site-packages so it inherits the floor
# packages below, and the pool is created with skip_environment_setup=True so
# no venv/pip commands run at container creation (which would require network).
#
# Built and tagged as agentgraphstudio-sandbox-floor:latest — see `make sandbox-image`.

# The upstream llm-sandbox image carries a build toolchain and a broad scientific
# stack that this floor does not use. The library only requires a Python image
# with pip and a shell when environment setup is skipped.
FROM python:3.14-slim-trixie

# Floor packages baked into the system interpreter. Bytecode is compiled at
# build time so pooled sessions never pay an import-compile cost inside each
# container.
RUN pip install --no-cache-dir matplotlib plotly numpy

# Bake the venv the pooled sessions execute against. --system-site-packages lets
# it see the floor packages above, so no per-container install is needed.
RUN mkdir -p /sandbox \
    && python -m venv --system-site-packages /sandbox/.sandbox-venv

WORKDIR /sandbox