"""PROTOTYPE — throwaway TUI for issue #81 (Runtime representation &
consumption of attachment instances).

Run: uv run python scripts/prototype_runtime_representation/tui.py   (from backend/)

Lets you cycle through four candidate policies and eight scenarios (six
input-side, two output-side — see scenarios.py) to react to how each policy
represents an attachment to the LLM, whether/when it materializes a file
inside the Docker sandbox, and how a sandbox-computed output attachment gets
captured without the LM re-typing it. Not production code — the pure logic
in logic.py is what would get lifted into the real module once a policy is
picked (see issue #81).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prototype_runtime_representation.logic import (  # noqa: E402
    Policy,
    plan_input_representation,
    plan_output_capture,
)
from prototype_runtime_representation.scenarios import INPUT_SCENARIOS, OUTPUT_SCENARIOS  # noqa: E402

BOLD = "\x1b[1m"
DIM = "\x1b[2m"
RESET = "\x1b[0m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"

POLICIES = list(Policy)
SCENARIOS = [("input", s) for s in INPUT_SCENARIOS] + [("output", s) for s in OUTPUT_SCENARIOS]


def clear() -> None:
    print("\033[2J\033[H", end="")


def render_input(policy: Policy, scenario: dict) -> None:
    attachment = scenario["attachment"]
    agent = scenario["agent"]
    plan = plan_input_representation(policy, attachment, agent)

    print(f"{BOLD}Attachment:{RESET} {attachment.name} ({attachment.file_type}, {attachment.size_bytes:,}B)")
    print(f"{BOLD}Consuming agent:{RESET} {agent.name}  coding_enabled={agent.coding_enabled}\n")

    print(f"{BOLD}LLM representation:{RESET} {plan.llm_content_kind.value}")
    print(f"  {DIM}{plan.llm_content_preview[:200]!r}{RESET}\n")

    print(f"{BOLD}Sandbox materialization:{RESET} {plan.sandbox_write}")
    print(f"  path={plan.sandbox_path!r}  timing={plan.sandbox_timing}\n")

    print(f"{BOLD}Notes:{RESET}")
    if not plan.notes:
        print(f"  {DIM}(none){RESET}")
    for n in plan.notes:
        print(f"  {YELLOW}- {n}{RESET}")


def render_output(policy: Policy, scenario: dict) -> None:
    draft = scenario["draft"]
    outcome = plan_output_capture(policy, draft)

    print(f"{BOLD}output_attachments draft (per #78):{RESET}")
    print(f"  name={draft.name!r} file_type={draft.file_type!r} content={draft.content[:60]!r}\n")

    color = GREEN if outcome.resolved else RED
    print(f"{BOLD}Resolved:{RESET} {color}{outcome.resolved}{RESET}")
    print(f"{BOLD}Stored content source:{RESET} {outcome.stored_content_source}\n")

    print(f"{BOLD}Notes:{RESET}")
    for n in outcome.notes:
        print(f"  {YELLOW}- {n}{RESET}")


def render(policy_idx: int, scenario_idx: int) -> None:
    clear()
    policy = POLICIES[policy_idx]
    kind, scenario = SCENARIOS[scenario_idx]

    print(f"{BOLD}Runtime representation & consumption prototype{RESET}  {DIM}(issue #81){RESET}\n")
    print(f"{BOLD}Policy:{RESET} {policy.value}  {DIM}[{policy_idx + 1}/{len(POLICIES)}]{RESET}")
    print(f"{BOLD}Scenario:{RESET} {scenario['label']}  {DIM}[{scenario_idx + 1}/{len(SCENARIOS)}]{RESET}\n")

    if kind == "input":
        render_input(policy, scenario)
    else:
        render_output(policy, scenario)

    print()
    print(
        f"{BOLD}[m]{RESET}{DIM} cycle policy{RESET}  "
        f"{BOLD}[n]{RESET}{DIM}/{RESET}{BOLD}[p]{RESET}{DIM} next/prev scenario{RESET}  "
        f"{BOLD}[q]{RESET}{DIM} quit{RESET}"
    )


def main() -> None:
    policy_idx = 0
    scenario_idx = 0
    render(policy_idx, scenario_idx)
    while True:
        key = input("\n> ").strip().lower()
        if key == "q":
            break
        if key == "m":
            policy_idx = (policy_idx + 1) % len(POLICIES)
        elif key == "n":
            scenario_idx = (scenario_idx + 1) % len(SCENARIOS)
        elif key == "p":
            scenario_idx = (scenario_idx - 1) % len(SCENARIOS)
        render(policy_idx, scenario_idx)


if __name__ == "__main__":
    main()
