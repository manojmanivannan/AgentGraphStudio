"""Connectivity probes used by the Settings page Test button.

Probes never raise on provider failure — a failed probe is reported as a
result entry so the UI can show which half of the configuration is broken.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import dspy

from canvas_server.config import settings
from canvas_server.provider_config import ProviderConfig

logger = logging.getLogger("canvas_server.provider_probe")


@dataclass
class ProbeResult:
    name: str
    ok: bool
    detail: str
    latency_ms: int


def _summarize(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if "<html" in lowered or "<!doctype" in lowered:
        return "The endpoint returned an HTML page — check the base URL."
    if isinstance(exc, TimeoutError):
        return f"Timed out after {settings.llm_validation_timeout_seconds}s."
    if "401" in text or "Unauthorized" in text or "AuthenticationError" in type(exc).__name__:
        return "401 Unauthorized — the API key is missing, invalid, or expired."
    if "404" in text:
        return "404 Not Found — check the base URL and model name."
    if "429" in text:
        return "429 Too Many Requests — rate limit exceeded."
    return text[:300] + ("..." if len(text) > 300 else "")


async def _timed(name: str, coro_factory) -> ProbeResult:
    start = time.perf_counter()
    try:
        await asyncio.wait_for(
            coro_factory(), timeout=settings.llm_validation_timeout_seconds
        )
    except Exception as exc:
        logger.info("Provider probe %r failed: %s", name, exc)
        return ProbeResult(
            name=name,
            ok=False,
            detail=_summarize(exc),
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
    return ProbeResult(
        name=name,
        ok=True,
        detail="OK",
        latency_ms=int((time.perf_counter() - start) * 1000),
    )


async def probe_provider(config: ProviderConfig) -> list[ProbeResult]:
    """Probe the chat model and the embedder independently."""

    async def chat() -> None:
        lm = dspy.LM(
            config.llm_model,
            api_base=config.llm_base_url,
            api_key=config.llm_api_key,
        )
        await lm.acall(prompt="Test connection. Respond with 'ok'.", max_tokens=5)

    async def embedding() -> None:
        from canvas_server.runner.rag_helper import get_embedder

        embedder = get_embedder(config)
        vectors = await asyncio.to_thread(embedder, ["connection test"])
        vector = vectors[0]
        dims = len(vector.tolist() if hasattr(vector, "tolist") else list(vector))
        if dims != config.mem0_embedder_dimensions:
            raise ValueError(
                f"Model returned {dims}-dimensional vectors but the configured "
                f"dimension is {config.mem0_embedder_dimensions}."
            )

    return list(
        await asyncio.gather(_timed("chat", chat), _timed("embedding", embedding))
    )
