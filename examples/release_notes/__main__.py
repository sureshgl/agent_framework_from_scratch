"""Demo: draft release notes from the sample changelog.

    python -m examples.release_notes [CHANGELOG_PATH]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .agent import build_agent

DEFAULT = str(Path(__file__).parent / "CHANGELOG.sample.md")


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set; the demo needs a live model.")
        return 1

    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    agent = build_agent(store_dir="runs")
    result = agent.run(f"Draft release notes from the changelog at {path}.")

    print(f"stop_reason={result.status}")
    if result.output is not None:
        print(f"\n{result.output.headline}\n")
        for h in result.output.highlights:
            print(f"  - {h}")
        if result.output.breaking:
            print("\nBreaking:")
            for b in result.output.breaking:
                print(f"  - {b}")
    print(f"\nevent log: {result.log_path}")
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
