"""Ask the agent from the terminal.

    python -m agent.cli "Which airports in New England are strong candidates for terminal expansion?"
    python -m agent.cli --examples          # runs the four assignment questions
    python -m agent.cli --tool rank_airports '{"region": "new england"}'   # call a tool directly, no LLM
"""
from __future__ import annotations

import argparse
import json
import sys

from agent import tools

EXAMPLES = [
    "Which airports in New England are strong candidates for terminal expansion?",
    "Compare LA and Santa Ana airport congestion levels.",
    "What is the percentage of long haul flights out of Anchorage airport?",
    "What is the unmet flight demand in SFO airport and why?",
]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("question", nargs="*")
    p.add_argument("--examples", action="store_true")
    p.add_argument("--tool", nargs=2, metavar=("NAME", "JSON_ARGS"))
    p.add_argument("--show-tools", action="store_true", help="print raw tool results")
    a = p.parse_args()

    if a.tool:
        print(tools.to_json(tools.run_tool(a.tool[0], json.loads(a.tool[1]))))
        return 0

    from agent.agent import AirportAgent  # imports anthropic, needs the key only here
    agent = AirportAgent()
    questions = EXAMPLES if a.examples else [" ".join(a.question)]
    if not questions[0]:
        p.print_help()
        return 1
    for q in questions:
        print(f"\n=== Q: {q}\n")
        turn = agent.ask(q)
        for c in turn.tool_calls:
            print(f"[tool] {c.name}({json.dumps(c.input)})")
            if a.show_tools:
                print(tools.to_json(c.result)[:3000])
        print()
        print(turn.text)
        print(f"\n[usage] {turn.usage}  stop={turn.stop_reason}")
        if a.examples:
            agent.reset()
    return 0


if __name__ == "__main__":
    sys.exit(main())
