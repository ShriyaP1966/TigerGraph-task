"""Stable interface for P3's Streamlit app. Signatures frozen: run_case, get_case,
list_pending_approvals, approve. ui.lib.data.load_cases() and mock_actions.py are
the swap points on P3's side.
"""
import csv
import json
from pathlib import Path

from actions.ledger import get_action, list_for_case, list_pending
from agent.graph import run_case as _run_case
from backends import get_backend
from contracts.ui_adapter import ACTION_TO_UI_ACTION, EVIDENCE_SOURCE_TO_UI_TYPE, TriggerInfo, UIDecision, UIEvidenceItem, UIExtras, UIFinding, now_iso, to_ui_case_record
from policy.gate import approval_gate as _approval_gate
from policy.gate import approve as _approve
from scoring.confidence import risk_level as _risk_level

REPO_ROOT = Path(__file__).resolve().parent
CASES_DIR = REPO_ROOT / "cases"

_backend = None
_case_pack_rows: dict | None = None


def _case_pack_row(case_id: str) -> dict | None:
    """cases/<id>.json (the Answer Format) doesn't carry the original trigger info or a
    customer_id that's always populated (sar.subjects is empty on any non-SAR case) -
    case_pack.csv has both, keyed by the same case_id, so get_case() cross-references it
    rather than guessing "unknown" or leaving fields blank."""
    global _case_pack_rows
    if _case_pack_rows is None:
        with (REPO_ROOT / "case_pack.csv").open(encoding="utf-8") as f:
            _case_pack_rows = {r["case_id"]: r for r in csv.DictReader(f)}
    return _case_pack_rows.get(case_id)


def _get_backend():
    global _backend
    if _backend is None:
        _backend = get_backend()
    return _backend


def run_case(trigger: dict) -> dict:
    """trigger: a case_pack.csv row as a dict (case_id, opened_at, trigger_type,
    trigger_text, flagged_txn_id, card_id, customer_id, risk_score)."""
    final_state = _run_case(trigger, _get_backend())
    case_record = final_state["case_record"]

    CASES_DIR.mkdir(exist_ok=True)
    (CASES_DIR / f"{case_record.case_id}.json").write_text(case_record.model_dump_json(indent=2), encoding="utf-8")

    return _to_ui_dict(final_state)


def get_case(case_id: str) -> dict | None:
    path = CASES_DIR / f"{case_id}.json"
    if not path.exists():
        return None
    from contracts.case_record import CaseRecord

    case_record = CaseRecord.model_validate_json(path.read_text(encoding="utf-8"))
    return _minimal_ui_dict(case_record)


def list_pending_approvals() -> list[dict]:
    return list_pending()


def approve(action_id: str, approver: str, decision: str = "approved") -> dict | None:
    result = _approve(action_id, approver, decision)
    return result


def _to_ui_dict(final_state: dict) -> dict:
    case_record = final_state["case_record"]
    extras = UIExtras(
        created_at=now_iso(),
        updated_at=now_iso(),
        trigger=TriggerInfo(type=final_state["trigger_type"], source_id=final_state["flagged_txn_id"], timestamp=final_state["opened_at"], details=final_state["trigger_text"]),
        customer_id=final_state["customer_id"],
        account_ids=[final_state["customer_id"]] + final_state.get("connected_card_ids", []),
        device_ids=final_state.get("device_profiles", []),
        evidence=[UIEvidenceItem(evidence_id=e["evidence_id"], type=e["type"], description=e["description"], source_tool=e["source_tool"], timestamp=e["timestamp"]) for e in final_state["evidence"]],
        findings=[UIFinding(finding_id="F1", description=case_record.case.summary, supporting_evidence=[e["evidence_id"] for e in final_state["evidence"]])],
        confidence_breakdown={k: v["value"] for k, v in final_state["confidence"]["breakdown"].items()},
        risk_level=final_state["confidence"]["risk_level"],
        decisions_and_actions=[
            UIDecision(
                decision_id=r["action_id"], decision=r["reason"], action=ACTION_TO_UI_ACTION.get(r["action"], "monitor_account"),
                requires_approval=r["route"] != "auto", approval_route=r["route"], status=r["status"],
                actor=r["actor"], timestamp=r["updated_at"],
            )
            for r in final_state.get("ledger_results", [])
        ],
        similar_prior_cases_detail={c["case_id"]: {"similarity_score": c["similarity"], "outcome": c["outcome"]} for c in final_state["similar_cases"]},
    )
    return to_ui_case_record(case_record, extras)


def _seed_ledger_if_empty(case_record) -> list[dict]:
    """The action ledger (actions.ledger, sqlite) only gets rows when a case runs
    through the live agent path (_to_ui_dict / policy.gate.approval_gate). Answer
    files loaded straight from cases/*.json (this environment's normal path, since
    the ledger is a gitignored local runtime artifact) never went through that, so
    list_for_case() comes back empty even though the case already has a real,
    persisted next_best_actions.final. Replay it through the same policy gate P2's
    live path uses - same route/auto-execute rules, no LLM call, nothing invented -
    so the approval queue and decision log are real and clicking Approve/Reject
    actually works, instead of silently staying empty forever for every reloaded
    case."""
    existing = list_for_case(case_record.case_id)
    if existing:
        return existing
    action_items = [{"action": a.action, "reason": a.reason} for a in case_record.next_best_actions.final]
    if not action_items:
        return []
    return _approval_gate(case_record.case_id, action_items, case_record.case.exposure_usd)


def _minimal_ui_dict(case_record) -> dict:
    """get_case() reload path - we don't have the full agent state anymore, just the
    written CaseRecord, so confidence_breakdown stays empty (that per-component
    number genuinely only exists in the ephemeral agent state, not the Answer
    Format - left honestly blank rather than invented). Everything else the Answer
    Format *does* carry (evidence, connected cards/devices, final next-best-actions)
    is mapped through here instead of being left empty. Trigger/customer_id come
    from case_pack.csv instead of guessing, since that's always available for any
    real case."""
    row = _case_pack_row(case_record.case_id) or {}
    evidence_items = [
        UIEvidenceItem(
            evidence_id=f"E{i + 1}",
            type=EVIDENCE_SOURCE_TO_UI_TYPE.get(e.source, e.source),
            description=e.claim,
            source_tool=e.ref,
            timestamp=row.get("opened_at", now_iso()),
        )
        for i, e in enumerate(case_record.case.evidence)
    ]
    ledger_rows = _seed_ledger_if_empty(case_record)
    extras = UIExtras(
        created_at=now_iso(),
        updated_at=now_iso(),
        trigger=TriggerInfo(
            type=row.get("trigger_type", "analyst_request"),
            source_id=case_record.case.first_suspicious_txn_id or row.get("flagged_txn_id", ""),
            timestamp=row.get("opened_at", now_iso()),
            details=row.get("trigger_text", ""),
        ),
        customer_id=row.get("customer_id") or (case_record.sar.subjects[0] if case_record.sar.subjects else ""),
        account_ids=case_record.case.connected_card_ids,
        device_ids=case_record.case.connected_device_profiles,
        evidence=evidence_items,
        findings=[UIFinding(finding_id="F1", description=case_record.case.summary, supporting_evidence=[e.evidence_id for e in evidence_items])] if evidence_items else [],
        confidence_breakdown={},
        risk_level=_risk_level(case_record.case.fraud_probability),
        decisions_and_actions=[
            UIDecision(
                decision_id=r["action_id"], decision=r["reason"], action=ACTION_TO_UI_ACTION.get(r["action"], "monitor_account"),
                requires_approval=r["route"] != "auto", approval_route=r["route"], status=r["status"],
                actor=r["actor"], timestamp=r["updated_at"],
            )
            for r in ledger_rows
        ],
        similar_prior_cases_detail={cc: {"similarity_score": 0.0, "outcome": "unknown"} for cc in case_record.case.similar_prior_cases},
    )
    return to_ui_case_record(case_record, extras)


def list_case_ids() -> list[str]:
    """All committed answer files' case_ids (cases/*.json), sorted - what P3's
    dashboard now loads by default instead of the 2-case mock contract."""
    return sorted(p.stem for p in CASES_DIR.glob("*.json")) if CASES_DIR.exists() else []
