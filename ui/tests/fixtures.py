"""Synthetic case records for stress-testing the dashboard before a live
agent exists. Each case is valid against contracts/case_record_schema.json
(all required fields present) but deliberately pushes at a different edge:
empty collections, null/out-of-vocabulary enum values, boundary scores,
very long or HTML-laden free text, large entity counts, etc.

This is what Phase 3 integration will surface once P2's agent (backed by an
LLM) starts generating real case records — better to find the rendering
bugs here, against synthetic data, than against a live demo.
"""

from __future__ import annotations

import copy
from typing import Any


def _base(case_id: str, **overrides: Any) -> dict[str, Any]:
    case: dict[str, Any] = {
        "case_id": case_id,
        "created_at": "2026-09-22T04:12:00Z",
        "updated_at": "2026-09-22T04:19:00Z",
        "status": "pending_approval",
        "trigger": {
            "type": "risk_score",
            "source_id": "TXN-0000001",
            "timestamp": "2026-09-22T04:10:00Z",
            "details": "Bank fraud model returned risk_score=0.80 on a $500 transaction.",
        },
        "entities": {
            "customer_id": "CUST-00001",
            "account_ids": ["ACCT-00001"],
            "transaction_ids": ["TXN-0000001"],
            "device_ids": ["DEV-00001"],
        },
        "investigation_record": {
            "entities_examined": ["ACCT-00001"],
            "evidence_gathered": [
                {
                    "evidence_id": "E1",
                    "type": "graph_pattern",
                    "description": "Baseline synthetic evidence entry.",
                    "source_tool": "synthetic_tool",
                    "timestamp": "2026-09-22T04:13:00Z",
                }
            ],
            "findings": [
                {"finding_id": "F1", "description": "Baseline synthetic finding.", "supporting_evidence": ["E1"]}
            ],
            "fraud_pattern_identified": "TYP-001",
            "risk_assessment": {
                "confidence_score": 0.6,
                "confidence_breakdown": {
                    "bank_risk_score": 0.6,
                    "typology_match_strength": 0.5,
                    "similarity_to_confirmed_fraud": 0.4,
                    "evidence_coverage_ratio": 0.5,
                },
                "risk_level": "medium",
                "rationale": "Baseline synthetic rationale.",
            },
        },
        "decisions_and_actions": [
            {
                "decision_id": "D1",
                "decision": "Baseline synthetic decision.",
                "action": "monitor_account",
                "requires_approval": False,
                "approval_route": "auto",
                "status": "executed",
                "actor": "agent",
                "timestamp": "2026-09-22T04:19:00Z",
            }
        ],
        "additional_evidence_requests": [],
        "next_best_action": {
            "before_additional_evidence": {
                "action": "monitor_account",
                "approval_route": "auto",
                "rationale": "Baseline before rationale.",
            },
            "after_additional_evidence": {
                "action": "monitor_account",
                "approval_route": "auto",
                "rationale": "Baseline after rationale.",
            },
        },
        "sar": {"filed": False, "content": None, "policy_clause_ids": []},
        "explanation": "Baseline synthetic explanation.",
        "case_memory": {"stored": True, "similar_prior_cases_used": []},
    }
    _deep_update(case, overrides)
    return case


def _deep_update(target: dict[str, Any], overrides: dict[str, Any]) -> None:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def build_stress_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    # 1. Rich, well-formed fraud case (baseline high end)
    cases.append(
        _base(
            "STRESS-01-baseline-fraud",
            status="closed_fraud",
            investigation_record={"risk_assessment": {"confidence_score": 0.92, "risk_level": "high"}},
            sar={"filed": True, "content": "Confirmed card-testing pattern.", "policy_clause_ids": ["POL-008"]},
        )
    )

    # 2. Well-formed legitimate case (baseline low end)
    cases.append(
        _base(
            "STRESS-02-baseline-legit",
            status="closed_cleared",
            investigation_record={"risk_assessment": {"confidence_score": 0.1, "risk_level": "low"}},
        )
    )

    # 3. Every collection empty
    cases.append(
        _base(
            "STRESS-03-empty-collections",
            investigation_record={"evidence_gathered": [], "findings": [], "fraud_pattern_identified": None},
            decisions_and_actions=[],
        )
    )

    # 4. Out-of-vocabulary risk_level + null pattern (tests badge fallback, not a crash)
    cases.append(
        _base(
            "STRESS-04-unknown-risk-level",
            investigation_record={
                "fraud_pattern_identified": None,
                "risk_assessment": {"risk_level": "critical"},  # not in RISK_LEVEL_STYLE
            },
        )
    )

    # 5. Confidence score boundary: 0.0
    cases.append(_base("STRESS-05-confidence-zero", investigation_record={"risk_assessment": {"confidence_score": 0.0}}))

    # 6. Confidence score boundary: 1.0
    cases.append(_base("STRESS-06-confidence-one", investigation_record={"risk_assessment": {"confidence_score": 1.0}}))

    # 7. Empty entities entirely -> graph should show its empty-state message, not crash
    cases.append(
        _base(
            "STRESS-07-empty-entities",
            entities={"customer_id": None, "account_ids": [], "transaction_ids": [], "device_ids": []},
        )
    )

    # 8. Large entity counts -> queue/graph at scale
    cases.append(
        _base(
            "STRESS-08-many-transactions",
            entities={
                "customer_id": "CUST-00008",
                "account_ids": ["ACCT-00008-A", "ACCT-00008-B"],
                "transaction_ids": [f"TXN-0008{n:03d}" for n in range(30)],
                "device_ids": ["DEV-00008"],
            },
        )
    )

    # 9. SAR filed citing a policy clause id that doesn't exist in loaded chunks
    cases.append(
        _base(
            "STRESS-09-sar-unknown-clause",
            sar={"filed": True, "content": "SAR citing an unknown clause.", "policy_clause_ids": ["POL-999"]},
        )
    )

    # 10. SAR filed with no clause ids at all
    cases.append(
        _base(
            "STRESS-10-sar-no-clauses",
            sar={"filed": True, "content": "SAR with nothing cited.", "policy_clause_ids": []},
        )
    )

    # 11. Very long free text everywhere
    _long_text = "This is a long synthetic narrative sentence written by a hypothetical LLM. " * 40
    cases.append(
        _base(
            "STRESS-11-long-text",
            explanation=_long_text,
            investigation_record={
                "risk_assessment": {"rationale": _long_text},
                "findings": [{"finding_id": "F1", "description": _long_text, "supporting_evidence": ["E1"]}],
            },
            decisions_and_actions=[
                {
                    "decision_id": "D1",
                    "decision": _long_text,
                    "action": "escalate_to_analyst",
                    "requires_approval": False,
                    "approval_route": "auto",
                    "status": "recommended",
                    "actor": "agent",
                    "timestamp": "2026-09-22T04:19:00Z",
                }
            ],
        )
    )

    # 12. HTML / markup-breaking characters in every free-text field — the escaping regression test
    _nasty = "score < 0.70 & exposure > $500, name=\"O'Brien\" <script>alert(1)</script>"
    cases.append(
        _base(
            "STRESS-12-html-injection",
            trigger={"details": _nasty},
            explanation=_nasty,
            investigation_record={
                "risk_assessment": {"rationale": _nasty},
                "findings": [{"finding_id": "F1", "description": _nasty, "supporting_evidence": ["E1"]}],
                "evidence_gathered": [
                    {
                        "evidence_id": "E1",
                        "type": "graph_pattern",
                        "description": _nasty,
                        "source_tool": "synthetic_tool",
                        "timestamp": "2026-09-22T04:13:00Z",
                    }
                ],
            },
            decisions_and_actions=[
                {
                    "decision_id": "D1",
                    "decision": _nasty,
                    "action": "block_transaction",
                    "requires_approval": True,
                    "approval_route": "fraud_analyst",
                    "status": "recommended",
                    "actor": "agent",
                    "timestamp": "2026-09-22T04:19:00Z",
                }
            ],
            sar={"filed": True, "content": _nasty, "policy_clause_ids": []},
        )
    )

    # 13. Unicode / emoji content
    _unicode_text = "客户报告可疑交易 🚨 — possible unauthorized use, café purchase in Zürich."
    cases.append(
        _base(
            "STRESS-13-unicode",
            explanation=_unicode_text,
            trigger={"details": _unicode_text},
        )
    )

    # 14. Out-of-vocabulary case status (tests case_status_badge fallback)
    cases.append(_base("STRESS-14-unknown-status", status="archived"))

    # 15. Out-of-vocabulary action name on a decision
    cases.append(
        _base(
            "STRESS-15-unknown-action",
            decisions_and_actions=[
                {
                    "decision_id": "D1",
                    "decision": "A decision using an action not in the documented vocabulary.",
                    "action": "notify_regulator_custom",
                    "requires_approval": True,
                    "approval_route": "compliance_officer",
                    "status": "pending_approval",
                    "actor": "agent",
                    "timestamp": "2026-09-22T04:19:00Z",
                }
            ],
        )
    )

    # 16. Missing optional free-text fields (empty strings / no actor)
    cases.append(
        _base(
            "STRESS-16-missing-optional-text",
            trigger={"details": ""},
            investigation_record={"risk_assessment": {"rationale": ""}},
            decisions_and_actions=[
                {
                    "decision_id": "D1",
                    "action": "warn_customer",
                    "requires_approval": False,
                    "approval_route": "auto",
                    "status": "executed",
                    "timestamp": "2026-09-22T04:19:00Z",
                }
            ],
            explanation="",
        )
    )

    # 17. next_best_action unchanged (before == after)
    cases.append(
        _base(
            "STRESS-17-nba-unchanged",
            next_best_action={
                "before_additional_evidence": {"action": "allow_transaction", "approval_route": "auto", "rationale": "Low risk."},
                "after_additional_evidence": {"action": "allow_transaction", "approval_route": "auto", "rationale": "Low risk."},
            },
        )
    )

    # 18. next_best_action escalates after evidence (before != after)
    cases.append(
        _base(
            "STRESS-18-nba-escalated",
            next_best_action={
                "before_additional_evidence": {"action": "verify_with_customer", "approval_route": "auto", "rationale": "Ambiguous."},
                "after_additional_evidence": {"action": "block_transaction", "approval_route": "fraud_analyst", "rationale": "Customer denied."},
            },
            additional_evidence_requests=[
                {
                    "request_id": "R1",
                    "requested_at": "before_initial_assessment",
                    "type": "account_owner_validation",
                    "reason": "Confirm or deny the transaction.",
                    "status": "received",
                    "result": "Customer denied making the purchase.",
                }
            ],
        )
    )

    # 19. Many similar prior cases -> case_memory list + graph SIMILAR_TO edges at scale
    cases.append(
        _base(
            "STRESS-19-many-similar-cases",
            case_memory={
                "stored": True,
                "similar_prior_cases_used": [
                    {"case_id": f"CC-{n:04d}", "similarity_score": round(0.5 + n * 0.03, 2), "outcome": "confirmed_fraud"}
                    for n in range(12)
                ],
            },
        )
    )

    # 20. Multiple decisions with mixed already-resolved statuses (approvals queue must only
    #     surface the one still pending, not the executed/rejected ones)
    cases.append(
        _base(
            "STRESS-20-mixed-decision-statuses",
            decisions_and_actions=[
                {
                    "decision_id": "D1",
                    "decision": "Already executed automatically.",
                    "action": "monitor_account",
                    "requires_approval": False,
                    "approval_route": "auto",
                    "status": "executed",
                    "actor": "agent",
                    "timestamp": "2026-09-22T04:15:00Z",
                },
                {
                    "decision_id": "D2",
                    "decision": "Already rejected by an analyst previously.",
                    "action": "block_transaction",
                    "requires_approval": True,
                    "approval_route": "fraud_analyst",
                    "status": "rejected",
                    "actor": "analyst_jane",
                    "timestamp": "2026-09-22T04:17:00Z",
                },
                {
                    "decision_id": "D3",
                    "decision": "Still awaiting sign-off.",
                    "action": "freeze_account",
                    "requires_approval": True,
                    "approval_route": "compliance_officer",
                    "status": "pending_approval",
                    "actor": "agent",
                    "timestamp": "2026-09-22T04:19:00Z",
                },
            ],
        )
    )

    return copy.deepcopy(cases)
