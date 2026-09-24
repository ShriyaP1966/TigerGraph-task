import json
import sys
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from contracts.case_record import ActionItem, Case, CaseRecord, Evidence, NextBestActions, SAR
from contracts.ui_adapter import TriggerInfo, UIDecision, UIEvidenceItem, UIExtras, UIFinding, now_iso, to_ui_case_record


def _sample_case_record() -> CaseRecord:
    return CaseRecord(
        case_id="HHG-001",
        case=Case(
            status="closed_fraud",
            verdict="fraud",
            fraud_probability=0.86,
            pattern="card_testing",
            affected_txn_ids=["T1", "T2"],
            first_suspicious_txn_id="T1",
            exposure_usd=268.43,
            evidence=[Evidence(claim="testing burst", source="graph", ref="velocity", entity_ids=["T1", "T2"])],
            similar_prior_cases=["CC-0141"],
            summary="Card testing pattern, blocked.",
            written_to_graph=True,
            graph_case_id="CASE-2016-1187",
        ),
        next_best_actions=NextBestActions(
            initial=[ActionItem(action="VERIFY_WITH_CUSTOMER", route="auto", reason="R1: single signal")],
            final=[ActionItem(action="BLOCK_CARD", route="L1", reason="R2: customer denied")],
            what_changed="Customer denial raised probability.",
        ),
        sar=SAR(file=True, reason="R2: exceeds $1000 threshold", narrative="...", subjects=["C12382"], total_amount_usd=268.43, activity_dates=["2016-12-05", "2016-12-05"]),
        stop_reason="Customer denial settled it.",
        tool_calls=5,
        tokens=1000,
        latency_s=2.1,
    )


def test_to_ui_case_record_matches_schema():
    case = _sample_case_record()
    extras = UIExtras(
        created_at=now_iso(),
        updated_at=now_iso(),
        trigger=TriggerInfo(type="risk_score", source_id="T1", timestamp=now_iso(), details="risk 0.61"),
        customer_id="C12382",
        account_ids=["C12382"],
        device_ids=[],
        evidence=[UIEvidenceItem(evidence_id="EV-001", type="graph_pattern", description="testing burst", source_tool="get_transaction_velocity", timestamp=now_iso())],
        findings=[UIFinding(finding_id="F1", description="card testing", supporting_evidence=["EV-001"])],
        confidence_breakdown={"bank_risk_score": 0.3, "typology_match_strength": 0.3, "similarity_to_confirmed_fraud": 0.2, "evidence_coverage_ratio": 0.06},
        risk_level="high",
        decisions_and_actions=[
            UIDecision(decision_id="D1", decision="block", action="block_transaction", requires_approval=True, approval_route="L1", status="pending_approval", timestamp=now_iso())
        ],
        similar_prior_cases_detail={"CC-0141": {"similarity_score": 0.87, "outcome": "confirmed_fraud"}},
    )

    ui_record = to_ui_case_record(case, extras)

    schema = json.loads((REPO_ROOT / "contracts" / "case_record_schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(ui_record, schema)


if __name__ == "__main__":
    test_to_ui_case_record_matches_schema()
    print("ui adapter matches case_record_schema.json")
