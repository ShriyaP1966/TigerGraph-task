"""Data-loading layer for the analyst dashboard.

Cases load from the real agent output: cases/*.json (the 20 graded answer
files, via api.get_case()) when any exist, else falling back to the shared
mock contract file (contracts/case_record_example.json) so the dashboard
still runs standalone against Phase 2's mock data in an environment with no
answer files yet. This is the only place that knows where case data comes
from — every component downstream only depends on the case dict shape, not
on where it came from.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MOCK_CASES_PATH = REPO_ROOT / "contracts" / "case_record_example.json"
POLICY_CLAUSES_PATH = REPO_ROOT / "docs" / "policy" / "chunks" / "policy_clauses.json"
TYPOLOGIES_PATH = REPO_ROOT / "docs" / "policy" / "chunks" / "typologies.json"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_real_cases() -> list[dict[str, Any]]:
    import api

    case_ids = api.list_case_ids()
    cases = []
    for case_id in case_ids:
        case = api.get_case(case_id)
        if case is not None:
            cases.append(case)
    return cases


def load_cases() -> list[dict[str, Any]]:
    """Load case records shaped like contracts/case_record_schema.json.

    Source: the real cases/*.json answer files via api.get_case() (which
    also seeds the real policy-gate ledger per case on first load, so the
    Approvals queue and decision log are live, not mocked). Falls back to
    contracts/case_record_example.json only if cases/ has no answer files
    yet (e.g. a fresh checkout before run_benchmark.py has run).
    """
    try:
        real_cases = _load_real_cases()
    except Exception:
        real_cases = []
    if real_cases:
        return real_cases
    if not MOCK_CASES_PATH.exists():
        return []
    return json.loads(MOCK_CASES_PATH.read_text(encoding="utf-8"))


def _load_chunks(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    chunks = json.loads(path.read_text(encoding="utf-8"))
    return {c["id"]: c for c in chunks}


def load_policy_clauses() -> dict[str, dict[str, Any]]:
    """POL-* id -> chunk dict (id, title, text, source_file), from the real
    chunked policy (docs/policy/chunks/policy_clauses.json)."""
    return _load_chunks(POLICY_CLAUSES_PATH)


def load_typologies() -> dict[str, dict[str, Any]]:
    """TYP-* id -> chunk dict, from docs/policy/chunks/typologies.json."""
    return _load_chunks(TYPOLOGIES_PATH)


def get_case(cases: list[dict[str, Any]], case_id: str) -> dict[str, Any] | None:
    for c in cases:
        if c["case_id"] == case_id:
            return c
    return None
