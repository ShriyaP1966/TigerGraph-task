"""Human-in-the-loop approval workflow, backed by the real action ledger.

This used to be a local mock (a JSON file overlay); now it delegates to
api.py / actions.ledger (the real sqlite-backed policy gate P2's agent also
writes to), so Approve/Reject here are real decisions, not a demo-only
simulation. Function names/signatures are unchanged from the mock version
so app.py and components/approvals.py needed no edits.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def record_decision(case_id: str, decision_id: str, new_status: str, actor: str) -> None:
    """Approve or reject a pending decision via the real ledger.

    new_status must be 'approved' or 'rejected' (matches api.approve()'s
    `decision` vocabulary). case_id is accepted for interface compatibility
    with the old mock signature but isn't needed to look up the action —
    decision_id (the ledger's action_id, e.g. 'HHG-001-A1') is already
    globally unique.
    """
    import api

    api.approve(decision_id, actor, decision=new_status)


def apply_overlay(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """No-op now: lib.data.load_cases() already reads decisions_and_actions
    live from the real ledger on every call (via api.get_case()), so there
    is nothing left to overlay. Kept so app.py's call site didn't need to
    change."""
    return cases
