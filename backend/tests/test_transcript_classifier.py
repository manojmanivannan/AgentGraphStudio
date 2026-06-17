import json
from pathlib import Path

import pytest

from canvas_server.runner.transcript_classifier import classify_tool_result


def _load_contract_cases():
    contract_path = (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "transcript_tool_result_contract.json"
    )
    return json.loads(contract_path.read_text())


@pytest.mark.parametrize("case", _load_contract_cases())
def test_classify_tool_result_matches_shared_contract(case):
    result = classify_tool_result(
        tool_name=case["tool_name"],
        fallback_agent_name=case["fallback_agent_name"],
    )

    assert result.agent_name == case["expected_agent_name"]
    assert result.event_type == case["expected_event_type"]
