"""legacyagents demo | bench [--out results.json] [--check results.json]"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from . import bench
from .agent import LegacyAgent
from .gateway import LegacyGateway
from .tools import LegacyTools


def demo() -> None:
    with tempfile.TemporaryDirectory() as d, LegacyTools(LegacyGateway(Path(d))) as tools:
        agent = LegacyAgent(tools)
        for q in [
            "What's the balance on HR00100003?",
            "Is policy LM-002000004 still active?",
            "Compare HR00100001 and HR00100005",
            "List active accounts over $200,000",
            "Please freeze HR00100007, my card was stolen",
        ]:
            print(f"Q: {q}\n   tool={agent.answer(q)['tool']}  A: {agent.trace[-1]['answer']}")
        tools.approve("HR00100007", "F", "branch-supervisor", "CHG-1001")
        print("   (supervisor approves CHG-1001)")
        q = "Please freeze HR00100007, my card was stolen"
        print(f"Q: {q}\n   A: {agent.answer(q)['answer']}")
        print(f"Q: What changed on accounts today?\n   A: {agent.answer('What changed on accounts today?')['answer']}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="legacyagents")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    b = sub.add_parser("bench")
    b.add_argument("--out")
    b.add_argument("--check")
    a = p.parse_args(argv)
    if a.cmd == "demo":
        demo()
        return 0
    r = bench.run()
    print(json.dumps(r, indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(r, indent=2) + "\n")
    if a.check:
        want = bench.deterministic(json.loads(Path(a.check).read_text()))
        if bench.deterministic(r) != want:
            print("deterministic results differ from committed results.json", file=sys.stderr)
            return 1
        print("deterministic results match committed results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
