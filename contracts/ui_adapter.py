"""Bridges the Answer Format (contracts/case_record.py, the graded submission
shape) to P3's case_record_schema.json (what the Streamlit dashboard renders).

The two schemas model the same investigation at different granularity, so this
is a best-effort, documented-lossy mapping, not a lossless round trip:
- UI evidence_id / finding_id / decision_id don't exist in the Answer Format,
  so the agent carries them separately in UIExtras (it already tracks them
  internally for the LLM's evidence-citation post-check).
- UI's fraud_pattern_identified wants a TYP-* id; the Answer Format's pattern
  is a plain enum string, mapped via PATTERN_TO_TYPOLOGY below.
- SAR policy_clause_ids aren't in the Answer Format's sar.reason text (it just
  cites "R1"/"R2" rule numbers); extracted with a regex against the real
  policy_clauses.json so the mapping doesn't drift from the loaded content.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from contracts.case_record import CaseRecord

REPO_ROOT = Path(__file__).resolve().parent.parent

PATTERN_TO_TYPOLOGY = {
    "card_testing": "TYP-001",
    "card_not_present_fraud": "TYP-002",
    "card_not_present_new_device": "TYP-003",
    "out_of_region_use": "TYP-004",
    "account_takeover": "TYP-005",
}

STATUS_TO_UI = {
    "open": "open",
    "closed_fraud": "closed_fraud",
    "closed_legitimate": "closed_cleared",
    "escalated": "pending_approval",
}

EVIDENCE_SOURCE_TO_UI_TYPE = {
    "graph": "graph_pattern",
    "document": "policy",
    "customer": "customer_response",
    "external": "analyst_input",
}

# case_record_schema.json's decisions_and_actions[].action is a 10-value enum, much
# coarser than the Answer Format's 14 UPPERCASE policy actions - lowercasing the Answer
# Format name directly (e.g. BLOCK_CARD -> "block_card") isn't a valid UI enum value at
# all, so this maps down explicitly. Several of these collapse distinct actions into one
# UI value (documented per-line below), since the UI enum has no room for the distinction:
ACTION_TO_UI_ACTION = {
    "ALLOW_TRANSACTION": "allow_transaction",
    "DECLINE_TRANSACTION": "block_transaction",
    "MONITOR_CARD": "monitor_account",
    "MONITOR_CONNECTED_CARDS": "monitor_account",  # UI has no "monitor other accounts" distinct from "monitor this one"
    "WARN_CUSTOMER": "warn_customer",
    "VERIFY_WITH_CUSTOMER": "request_more_evidence",  # UI has no action-level distinction between the 3 evidence-request types
    "STEP_UP_AUTH": "request_more_evidence",
    "BLOCK_CARD": "freeze_account",  # closer to "freeze" (blocks + reissues) than "block_transaction" (declines just the one auth)
    "BLOCK_ALL_CARDS": "freeze_account",  # UI has no separate "freeze everything" from "freeze this account"
    "GENERATE_REPORT": "create_case",  # lossy: README defines GENERATE_REPORT as explicitly NOT opening a case; UI enum has no bare "write a report" action
    "CREATE_CASE": "create_case",
    "FILE_REPORT": "file_report",
    "ESCALATE_TO_ANALYST": "escalate_to_analyst",
    "CLOSE_NO_FRAUD": "close_case",
}


class TriggerInfo(BaseModel):
    type: str
    source_id: str
    timestamp: str
    details: str = ""


class UIEvidenceItem(BaseModel):
    evidence_id: str
    type: str
    description: str
    source_tool: str
    timestamp: str


class UIFinding(BaseModel):
    finding_id: str
    description: str
    supporting_evidence: list[str] = Field(default_factory=list)


class UIDecision(BaseModel):
    decision_id: str
    decision: str
    action: str
    requires_approval: bool
    approval_route: str
    status: str
    actor: str = "agent"
    timestamp: str


class UIExtras(BaseModel):
    """Everything the UI schema needs that the graded Answer Format doesn't carry.
    The agent builds this alongside the CaseRecord as it investigates."""

    created_at: str
    updated_at: str
    trigger: TriggerInfo
    customer_id: str
    account_ids: list[str] = Field(default_factory=list)
    device_ids: list[str] = Field(default_factory=list)
    evidence: list[UIEvidenceItem] = Field(default_factory=list)
    findings: list[UIFinding] = Field(default_factory=list)
    confidence_breakdown: dict[str, float] = Field(default_factory=dict)
    risk_level: str = "medium"
    decisions_and_actions: list[UIDecision] = Field(default_factory=list)
    similar_prior_cases_detail: dict[str, dict] = Field(
        default_factory=dict, description="case_id -> {similarity_score, outcome}, from get_prior_similar_cases"
    )


def _load_rule_to_clause() -> dict[str, str]:
    path = REPO_ROOT / "docs" / "policy" / "chunks" / "policy_clauses.json"
    if not path.exists():
        return {}
    clauses = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for c in clauses:
        m = re.match(r"(R\d+)\.", c.get("title", ""))
        if m:
            out[m.group(1)] = c["id"]
    return out


def _extract_policy_clause_ids(text: str) -> list[str]:
    rule_to_clause = _load_rule_to_clause()
    rules = re.findall(r"\bR\d+\b", text or "")
    return sorted({rule_to_clause[r] for r in rules if r in rule_to_clause})


def to_ui_case_record(case: CaseRecord, extras: UIExtras) -> dict:
    c = case.case
    nba = case.next_best_actions

    return {
        "case_id": case.case_id,
        "created_at": extras.created_at,
        "updated_at": extras.updated_at,
        "status": STATUS_TO_UI[c.status],
        "trigger": extras.trigger.model_dump(),
        "entities": {
            "customer_id": extras.customer_id,
            "account_ids": extras.account_ids,
            "transaction_ids": c.affected_txn_ids,
            "device_ids": extras.device_ids,
        },
        "investigation_record": {
            "entities_examined": extras.account_ids + extras.device_ids,
            "evidence_gathered": [e.model_dump() for e in extras.evidence],
            "findings": [f.model_dump() for f in extras.findings],
            "fraud_pattern_identified": PATTERN_TO_TYPOLOGY.get(c.pattern),
            "risk_assessment": {
                "confidence_score": c.fraud_probability,
                "confidence_breakdown": extras.confidence_breakdown,
                "risk_level": extras.risk_level,
                "rationale": c.summary,
            },
        },
        "decisions_and_actions": [d.model_dump() for d in extras.decisions_and_actions],
        "additional_evidence_requests": [
            {
                "request_id": f"R{i + 1}",
                "requested_at": "before_initial_assessment" if i == 0 else "after_initial_assessment",
                "type": {
                    "customer_validation": "account_owner_validation",
                    "step_up_auth": "step_up_authentication",
                    "analyst_info": "analyst_input",
                }[r.type],
                "reason": r.assumed_response,
                "status": "received",
                "result": r.assumed_response,
            }
            for i, r in enumerate(case.evidence_requests)
        ],
        "next_best_action": {
            "before_additional_evidence": {
                "action": nba.initial[0].action if nba.initial else "",
                "approval_route": nba.initial[0].route if nba.initial else "",
                "rationale": "; ".join(a.reason for a in nba.initial),
            },
            "after_additional_evidence": {
                "action": nba.final[0].action if nba.final else "",
                "approval_route": nba.final[0].route if nba.final else "",
                "rationale": "; ".join(a.reason for a in nba.final),
            },
        },
        "sar": {
            "filed": case.sar.file,
            "content": case.sar.narrative or None,
            "policy_clause_ids": _extract_policy_clause_ids(case.sar.reason),
        },
        "explanation": c.summary,
        "case_memory": {
            "stored": c.written_to_graph,
            "similar_prior_cases_used": [
                {
                    "case_id": cc,
                    "similarity_score": extras.similar_prior_cases_detail.get(cc, {}).get("similarity_score", 0.0),
                    "outcome": extras.similar_prior_cases_detail.get(cc, {}).get("outcome", "unknown"),
                }
                for cc in c.similar_prior_cases
            ],
        },
    }


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
