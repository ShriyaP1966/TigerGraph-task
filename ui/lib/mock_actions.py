"""Mock action API / audit ledger for the human-in-the-loop approval workflow.

Stands in for P2's real approve/reject + execute API. This module is
intentionally the only place that mutates a decision's status, so wiring up
the real API later means replacing record_decision()'s body — the
Approvals UI component calls this function and never touches storage
directly.

Ledger entries key on (case_id, decision_id) and are overlaid onto the
matching entry's status/actor/timestamp in decisions_and_actions at read
time via apply_overlay(); the underlying mock case file is never edited.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER_PATH = Path(__file__).resolve().parent.parent / ".local" / "audit_ledger.json"


def _load_ledger() -> dict[str, dict[str, dict[str, str]]]:
    if not LEDGER_PATH.exists():
        return {}
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def _save_ledger(ledger: dict[str, Any]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")


def record_decision(case_id: str, decision_id: str, new_status: str, actor: str) -> None:
    """Approve or reject a pending decision.

    new_status must be one of the case-record schema's
    decisions_and_actions[].status values — 'approved' or 'rejected' for
    this workflow.
    """
    ledger = _load_ledger()
    case_entries = ledger.setdefault(case_id, {})
    case_entries[decision_id] = {
        "status": new_status,
        "actor": actor,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _save_ledger(ledger)


def apply_overlay(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a deep copy of `cases` with recorded approve/reject decisions
    applied on top of decisions_and_actions[].status/actor/timestamp."""
    ledger = _load_ledger()
    if not ledger:
        return cases
    cases = copy.deepcopy(cases)
    for case in cases:
        overrides = ledger.get(case["case_id"])
        if not overrides:
            continue
        for decision in case.get("decisions_and_actions", []):
            override = overrides.get(decision["decision_id"])
            if override:
                decision["status"] = override["status"]
                decision["actor"] = override["actor"]
                decision["timestamp"] = override["timestamp"]
    return cases
