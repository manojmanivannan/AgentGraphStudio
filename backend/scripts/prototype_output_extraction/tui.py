"""PROTOTYPE — throwaway TUI for issue #78 (Output-extraction mechanism).

Run: uv run python scripts/prototype_output_extraction/tui.py   (from backend/)

Lets you cycle through the three candidate signaling mechanisms and six
scenarios (see scenarios.py) to react to how each one extracts, validates,
and times attachment capture relative to the ReAct loop. Not production code —
the pure logic in logic.py is what would get lifted into the real module once
a mechanism is picked (see issue #78).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prototype_output_extraction.logic import Mechanism, run, raw_view  # noqa: E402
from prototype_output_extraction.scenarios import SCENARIOS, SLOTS  # noqa: E402

BOLD = "\x1b[1m"
DIM = "\x1b[2m"
RESET = "\x1b[0m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"

MECHANISMS = list(Mechanism)


def clear() -> None:
    print("\033[2J\033[H", end="")


def render(mechanism_idx: int, scenario_idx: int) -> None:
    clear()
    mechanism = MECHANISMS[mechanism_idx]
    scenario = SCENARIOS[scenario_idx]
    outcome = run(mechanism, scenario, SLOTS)

    print(f"{BOLD}Output-extraction mechanism prototype{RESET}  {DIM}(issue #78){RESET}\n")
    print(f"{BOLD}Declared output Attachment slots on this agent:{RESET}")
    for slot in SLOTS:
        print(f"  - {slot.name} ({slot.file_type})")
    print()
    print(f"{BOLD}Mechanism:{RESET} {mechanism.value}  {DIM}[{mechanism_idx + 1}/{len(MECHANISMS)}]{RESET}")
    print(f"{BOLD}Scenario:{RESET}  {scenario['label']}  {DIM}[{scenario_idx + 1}/{len(SCENARIOS)}]{RESET}\n")

    print(f"{BOLD}Raw material fed to the extractor:{RESET}")
    print(DIM + raw_view(mechanism, scenario) + RESET)
    print()

    print(f"{BOLD}When extraction/validation happens:{RESET} {outcome.when}\n")

    print(f"{BOLD}Remaining final answer (what the UI shows as prose):{RESET}")
    print(f"  {outcome.remaining_answer!r}\n")

    print(f"{BOLD}Extracted attachment drafts:{RESET}")
    if not outcome.drafts:
        print(f"  {DIM}(none){RESET}")
    for d in outcome.drafts:
        print(f"  - name={d.name!r} file_type={d.file_type!r} origin={d.origin} content={d.content[:40]!r}")
    print()

    print(f"{BOLD}Validation errors:{RESET}")
    if not outcome.errors:
        print(f"  {GREEN}(none){RESET}")
    for e in outcome.errors:
        print(f"  {RED}- {e}{RESET}")
    print()

    print(
        f"{BOLD}[m]{RESET}{DIM} cycle mechanism{RESET}  "
        f"{BOLD}[n]{RESET}{DIM}/{RESET}{BOLD}[p]{RESET}{DIM} next/prev scenario{RESET}  "
        f"{BOLD}[q]{RESET}{DIM} quit{RESET}"
    )


def main() -> None:
    mechanism_idx = 0
    scenario_idx = 0
    render(mechanism_idx, scenario_idx)
    while True:
        key = input("\n> ").strip().lower()
        if key == "q":
            break
        if key == "m":
            mechanism_idx = (mechanism_idx + 1) % len(MECHANISMS)
        elif key == "n":
            scenario_idx = (scenario_idx + 1) % len(SCENARIOS)
        elif key == "p":
            scenario_idx = (scenario_idx - 1) % len(SCENARIOS)
        render(mechanism_idx, scenario_idx)


if __name__ == "__main__":
    main()
