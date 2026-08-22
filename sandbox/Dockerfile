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

FROM ghcr.io/vndee/sandbox-python-311-bullseye

# Floor packages baked into the system interpreter.
RUN pip install --no-cache-dir matplotlib plotly numpy

# Bake the venv the pooled sessions execute against. --system-site-packages lets
# it see the floor packages above, so no per-container install is needed.
RUN mkdir -p /sandbox \
    && python -m venv --system-site-packages /sandbox/.sandbox-venv

WORKDIR /sandbox