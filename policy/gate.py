from datetime import datetime, timezone
from pathlib import Path

import json

from actions.ledger import get_action, list_for_case, log_action, update_status

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_TABLE = json.loads((REPO_ROOT / "policy" / "policy_table.json").read_text(encoding="utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_route(action: str, exposure_usd: float) -> str:
    entry = POLICY_TABLE.get(action)
    if entry is None:
        return "L2"  # unknown action, fail safe to the strictest route
    if entry["route"] != "conditional":
        return entry["route"]
    return "L1" if exposure_usd <= entry["amount_threshold"] else "L2"


def is_auto_executable(action: str) -> bool:
    return resolve_route(action, exposure_usd=0) == "auto"


def approval_gate(case_id: str, action_items: list[dict], exposure_usd: float) -> list[dict]:
    """action_items: [{"action": str, "reason": str}, ...] (route from the LLM/agent is
    re-derived here, never trusted - the policy table is the one source of truth)."""
    existing = list_for_case(case_id)
    n = len(existing)
    results = []
    for item in action_items:
        n += 1
        action_id = f"{case_id}-A{n}"
        route = resolve_route(item["action"], exposure_usd)
        status = "executed" if route == "auto" else "pending_approval"
        log_action(action_id, case_id, item["action"], route, item.get("reason", ""), status, "agent", _now())
        results.append(get_action(action_id))
    return results


def approve(action_id: str, approver: str, decision: str = "approved") -> dict | None:
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be 'approved' or 'rejected'")
    existing = get_action(action_id)
    if existing is None:
        return None
    status = "executed" if decision == "approved" else "rejected"
    update_status(action_id, status, approver, _now())
    return get_action(action_id)
