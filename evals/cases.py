"""Eval cases and the (pure, unit-testable) scorer.

Report cases E1-E7 reconcile one seeded invoice each and score the resulting
verdict against `answer_key.json`. E8 and E9 are runtime-behavior cases (budget
exhaustion, deny-on-resume) handled directly in `run.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

ANSWER_KEY: dict[str, dict] = json.loads(
    (Path(__file__).parent / "answer_key.json").read_text(encoding="utf-8")
)

# (eval id, invoice id). Order matches spec §13.
REPORT_CASES: list[tuple[str, str]] = [
    ("E1", "INV-9001"),
    ("E2", "INV-9002"),
    ("E3", "INV-9003"),
    ("E4", "INV-9004"),
    ("E5", "INV-9005"),
    ("E6", "INV-9006"),
    ("E7", "INV-9007"),
]


def score_verdict(verdict, expected: dict) -> list[tuple[str, bool]]:
    """Return a list of (check_name, passed). A case passes iff all checks pass."""
    checks: list[tuple[str, bool]] = [
        ("recommendation", verdict.recommendation == expected["recommendation"]),
    ]
    if expected.get("three_way_match"):
        checks.append(("three_way_match", verdict.three_way_match == expected["three_way_match"]))
    if expected.get("vendor_verified") is not None:
        checks.append(("vendor_verified", verdict.vendor_verified == expected["vendor_verified"]))
    if expected.get("duplicate_of"):
        checks.append(("duplicate_of", verdict.duplicate_of == expected["duplicate_of"]))
    issue = expected.get("issue")
    if issue and issue != "ok":
        found = {f.issue for f in verdict.findings}
        checks.append((f"issue:{issue}", issue in found))
    return checks


def all_passed(checks: list[tuple[str, bool]]) -> bool:
    return all(ok for _, ok in checks)


def failed_checks(checks: list[tuple[str, bool]]) -> list[str]:
    return [name for name, ok in checks if not ok]
