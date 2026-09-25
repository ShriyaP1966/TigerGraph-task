"""Proves validate_answer_file.py actually catches what it claims to.

- fixtures/valid_answer_example.json is DATASET_README.md's own worked example
  (HHG-017) copied verbatim — must validate clean, including the real
  cross-checks against case_pack.csv and closed_cases_history.csv.
- fixtures/invalid_answer_example.json deliberately breaks close to every
  rule the validator checks — must produce a specific, expected error for
  each one.

Run: python scripts/tests/test_validate_answer_file.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from validate_answer_file import _load_case_pack_ids, _load_closed_case_ids, validate_answer  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Substrings expected to appear somewhere in the invalid fixture's error list —
# one per rule being exercised, so a regression in any single check shows up
# as a specific named failure rather than just "error count changed".
EXPECTED_INVALID_SUBSTRINGS = [
    "case_id: 'HHG-999' is not one of the 20",
    "case.pattern: 'phishing'",
    'case.pattern_description: must be ""',
    "must be empty when verdict is 'legitimate'",
    "must be 0 when verdict is 'legitimate'",
    "case.evidence[0].claim",
    "case.evidence[0].source",
    "'CC-9999' is not a case_id in closed_cases_history.csv",
    "evidence_requests[0].type",
    "evidence_requests[0].asked_after_step",
    "evidence_requests[0].assumed_response",
    "FREEZE_EVERYTHING",
    "BLOCK_ALL_CARDS must have route 'L2'",
    "BLOCK_CARD with exposure_usd=5000 must have route 'L2'",
    "next_best_actions.what_changed",
    "sar.file=True does not agree with whether FILE_REPORT appears",
    "sar.narrative: required",
    "sar.subjects: required",
    "sar.activity_dates: must be a list of exactly two",
    "missing required field 'stop_reason'",
    "missing required field 'tokens'",
    "tool_calls: must be an integer",
    "latency_s: must be a number",
]


def main() -> int:
    known_case_ids = _load_case_pack_ids()
    known_closed_case_ids = _load_closed_case_ids()
    if not known_case_ids or not known_closed_case_ids:
        print("FAIL: case_pack.csv / closed_cases_history.csv not found — cannot run cross-check tests.")
        return 1

    ok = True

    # --- valid fixture must pass clean ---
    valid_data = json.loads((FIXTURES / "valid_answer_example.json").read_text(encoding="utf-8"))
    valid_errors = validate_answer(valid_data, known_case_ids, known_closed_case_ids)
    if valid_errors:
        ok = False
        print(f"FAIL: valid_answer_example.json should have 0 errors, got {len(valid_errors)}:")
        for e in valid_errors:
            print(f"    - {e}")
    else:
        print("PASS: valid_answer_example.json (DATASET_README.md's own HHG-017 example) validates clean.")

    # --- invalid fixture must catch every planted issue ---
    invalid_data = json.loads((FIXTURES / "invalid_answer_example.json").read_text(encoding="utf-8"))
    invalid_errors = validate_answer(invalid_data, known_case_ids, known_closed_case_ids)
    joined = "\n".join(invalid_errors)

    print(f"\ninvalid_answer_example.json produced {len(invalid_errors)} error(s). Checking expected ones fired:")
    for expected in EXPECTED_INVALID_SUBSTRINGS:
        found = expected in joined
        print(f"  [{'x' if found else ' '}] {expected}")
        if not found:
            ok = False

    print()
    if ok:
        print("All validator behavior checks PASSED.")
        return 0
    print("Some validator behavior checks FAILED (see [ ] above).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
