"""Regression tests for the provider probe against dspy>=3.4.

dspy 3.4 replaced eager ``openai`` / ``litellm`` imports with lazy module
proxies. When dspy is imported before openai (the app's real import order),
litellm's ``from openai._models import BaseModel`` re-enters ``openai``'s
package init through the proxy mid-import and fails with
``cannot import name 'BaseModel' from partially initialized module
'openai._models'``. ``canvas_server/__init__.py`` imports openai eagerly to
prevent this.

The probe itself is exercised in a subprocess so the import order matches the
running app exactly: the package init runs first, then provider_probe (and the
lazily imported rag_helper) touch dspy/litellm/openai.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import canvas_server

_PROBE_SCRIPT = """
import asyncio
import json
import sys

import canvas_server.provider_probe  # noqa: F401 -- the app's first dspy import

from canvas_server.provider_config import ProviderConfig
from canvas_server.provider_probe import probe_provider

def make_config(api_key):
    return ProviderConfig(
        profile="probe",
        llm_provider_type="ollama",
        llm_base_url="http://127.0.0.1:1/v1",
        llm_api_key=api_key,
        llm_model="glm-5.3-flash:cloud",
        mem0_embedder_model="nomic-embed-text",
        mem0_embedder_dimensions=768,
    )

out = {"openai_is_lazy_proxy": type(sys.modules["openai"]).__name__ == "_LazyModule"}
for label, key in (("dummy_key", "sk-dummy"), ("empty_key", "")):
    results = asyncio.run(probe_provider(make_config(key)))
    out[label] = {r.name: r.detail for r in results}
print(json.dumps(out))
"""


def _reached_transport(detail: str) -> bool:
    # The connection to 127.0.0.1:1 fails instantly, but under a loaded full
    # suite the probe can hit its validation timeout instead; both are honest
    # transport-level failures, unlike an import/credential refusal.
    lowered = detail.lower()
    return "connect" in lowered or "timed out" in lowered


def _run_probe_script() -> dict:
    # Force the subprocess to the same src tree the tests import from.
    src_root = Path(canvas_server.__file__).resolve().parent.parent
    env = os.environ | {
        "PYTHONPATH": str(src_root) + os.pathsep + os.environ.get("PYTHONPATH", "")
    }
    result = subprocess.run(
        [sys.executable, "-c", _PROBE_SCRIPT],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_openai_is_fully_imported_above_dspy():
    # dspy's lazy proxy in sys.modules is what triggers the circular import.
    assert _run_probe_script()["openai_is_lazy_proxy"] is False


def test_embedding_probe_reports_connection_failure_not_import_error():
    detail = _run_probe_script()["dummy_key"]["embedding"].lower()
    assert "circular import" not in detail
    assert "basemodel" not in detail
    assert _reached_transport(detail)


def test_chat_probe_omits_empty_key_instead_of_refusing_credential():
    detail = _run_probe_script()["empty_key"]["chat"].lower()
    assert "empty credential" not in detail
    assert _reached_transport(detail)


def test_chat_probe_reaches_the_endpoint_with_a_key():
    detail = _run_probe_script()["dummy_key"]["chat"].lower()
    assert "empty credential" not in detail
    assert _reached_transport(detail)
