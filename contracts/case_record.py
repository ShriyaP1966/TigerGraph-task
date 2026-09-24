"""Pydantic models for the README1.md Answer Format — the graded submission shape.
This is the core model the agent builds and run_benchmark.py writes to cases/*.json.
Field names/enums are copied straight from the README, not invented.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["open", "closed_fraud", "closed_legitimate", "escalated"]
Verdict = Literal["fraud", "legitimate", "uncertain"]
Pattern = Literal[
    "card_testing",
    "card_not_present_fraud",
    "card_not_present_new_device",
    "out_of_region_use",
    "account_takeover",
    "undocumented",
    "none",
]
EvidenceSource = Literal["graph", "document", "customer", "external"]
EvidenceRequestType = Literal["customer_validation", "step_up_auth", "analyst_info"]
ApprovalRoute = Literal["auto", "L1", "L2"]
Action = Literal[
    "ALLOW_TRANSACTION",
    "DECLINE_TRANSACTION",
    "MONITOR_CARD",
    "MONITOR_CONNECTED_CARDS",
    "WARN_CUSTOMER",
    "VERIFY_WITH_CUSTOMER",
    "STEP_UP_AUTH",
    "BLOCK_CARD",
    "BLOCK_ALL_CARDS",
    "GENERATE_REPORT",
    "CREATE_CASE",
    "FILE_REPORT",
    "ESCALATE_TO_ANALYST",
    "CLOSE_NO_FRAUD",
]


class Evidence(BaseModel):
    claim: str
    source: EvidenceSource
    ref: str
    entity_ids: list[str] = Field(default_factory=list)


class EvidenceRequest(BaseModel):
    type: EvidenceRequestType
    asked_after_step: int
    assumed_response: str


class ActionItem(BaseModel):
    action: Action
    route: ApprovalRoute
    reason: str


class NextBestActions(BaseModel):
    initial: list[ActionItem]
    final: list[ActionItem]
    what_changed: str


class SAR(BaseModel):
    file: bool
    reason: str
    narrative: str = ""
    subjects: list[str] = Field(default_factory=list)
    total_amount_usd: float = 0
    activity_dates: list[str] = Field(default_factory=list)


class Case(BaseModel):
    status: Status
    verdict: Verdict
    fraud_probability: float = Field(ge=0, le=1)
    pattern: Pattern
    pattern_description: str = ""
    affected_txn_ids: list[str] = Field(default_factory=list)
    first_suspicious_txn_id: str = ""
    connected_card_ids: list[str] = Field(default_factory=list)
    connected_device_profiles: list[str] = Field(default_factory=list)
    exposure_usd: float = 0
    evidence: list[Evidence] = Field(default_factory=list)
    similar_prior_cases: list[str] = Field(default_factory=list)
    summary: str
    written_to_graph: bool = False
    graph_case_id: str = ""


class CaseRecord(BaseModel):
    case_id: str
    case: Case
    evidence_requests: list[EvidenceRequest] = Field(default_factory=list)
    next_best_actions: NextBestActions
    sar: SAR
    stop_reason: str
    tool_calls: int = 0
    tokens: int = 0
    latency_s: float = 0


def validate_case_record(cr: CaseRecord) -> list[str]:
    """Cross-field checks from README1.md's Answer Format, reusing P3's validator so
    we don't maintain two copies of the same rules."""
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root / "scripts") not in sys.path:
        sys.path.insert(0, str(repo_root / "scripts"))
    from validate_answer_file import _load_case_pack_ids, _load_closed_case_ids, validate_answer

    return validate_answer(cr.model_dump(mode="json"), _load_case_pack_ids(), _load_closed_case_ids())
