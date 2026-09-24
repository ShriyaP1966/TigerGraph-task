"""Data-loading layer for the analyst dashboard.

Cases currently load from the shared mock contract file
(contracts/case_record_example.json), matching
contracts/case_record_schema.json. This is the only place that knows where
case data comes from — pointing the dashboard at P2's live agent output
later means changing load_cases() here, not any component that renders it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CASES_PATH = REPO_ROOT / "contracts" / "case_record_example.json"
POLICY_CLAUSES_PATH = REPO_ROOT / "docs" / "policy" / "chunks" / "policy_clauses.json"
TYPOLOGIES_PATH = REPO_ROOT / "docs" / "policy" / "chunks" / "typologies.json"


def load_cases() -> list[dict[str, Any]]:
    """Load case records shaped like contracts/case_record_schema.json.

    Source today: contracts/case_record_example.json (P2's mock contract
    data). Swap this function's body for a read of P2's live agent output
    (file or API) when it lands — every component downstream only depends
    on the case dict shape, not on where it came from.
    """
    if not CASES_PATH.exists():
        return []
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


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
