"""LangGraph state. Plain dict, not a pydantic model - nodes read/write keys
directly and each node returns the full updated value for any key it touches
(no accumulation reducers needed since nodes always pass back complete lists)."""
from typing import Any, TypedDict


class CaseState(TypedDict, total=False):
    case_id: str
    backend: Any  # GraphBackend - never serialized, in-memory only

    trigger_type: str
    trigger_text: str
    opened_at: str
    flagged_txn_id: str
    card_id: str
    customer_id: str
    risk_score_input: float | None

    as_of: str | None
    flagged_txn: dict | None
    subgraph_txns: list
    device_profiles: list[str]

    evidence: list[dict]
    tool_calls: int

    ring: dict
    velocity_1h: dict
    velocity_48h: dict
    similar_cases: list[dict]
    policy_clauses: list[dict]
    typologies: list[dict]

    pattern: str
    pattern_description: str
    typology_match_strength: float
    confidence: dict
    confidence_before: dict
    verdict: str
    evidence_signal_count: int

    loop_count: int
    evidence_requests: list[dict]
    customer_response: str | None

    initial_actions: list[dict] | None
    final_actions: list[dict]
    what_changed: str

    affected_txn_ids: list[str]
    connected_card_ids: list[str]
    connected_device_profiles: list[str]
    exposure_usd: float
    already_cleared_amount: float

    sar: dict
    summary: str
    explanation: str
    stop_reason: str
    status: str

    ledger_results: list[dict]
    executed_actions: list[dict]
    tokens_est: int
    written_to_graph: bool
    graph_case_id: str
    similar_to: list[str]
    case_record: object

    start_time: float


def new_state(case_row: dict, backend) -> CaseState:
    import time

    return CaseState(
        case_id=case_row["case_id"],
        backend=backend,
        trigger_type=case_row["trigger_type"],
        trigger_text=case_row["trigger_text"],
        opened_at=case_row["opened_at"],
        flagged_txn_id=str(case_row["flagged_txn_id"]),
        card_id=case_row["card_id"],
        customer_id=case_row["customer_id"],
        risk_score_input=float(case_row["risk_score"]) if case_row.get("risk_score") not in (None, "", "nan") else None,
        evidence=[],
        tool_calls=0,
        loop_count=0,
        evidence_requests=[],
        customer_response=None,
        initial_actions=None,
        final_actions=[],
        what_changed="nothing",
        affected_txn_ids=[],
        connected_card_ids=[],
        connected_device_profiles=[],
        exposure_usd=0,
        already_cleared_amount=0,
        start_time=time.time(),
    )
