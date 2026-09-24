"""Input/output models for every GraphBackend method. Source of truth for P1 —
export_schemas() below writes these out as JSON Schema so tigergraph-mcp tools
can be built to match without importing this file.

as_of shows up on the evidence-gathering calls because a case can only see
transactions that happened at or before the flagged transaction's ts — no
future leakage into an investigation.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class TxnSummary(BaseModel):
    txn_id: str
    ts: str
    amount: float
    product_cd: str
    channel: str
    risk_score: float | None = None
    card_id: str | None = None
    device_new: bool | None = None  # identity.csv id_15 == "New" - None means no identity record (in_person)
    addr1: str | None = None  # billing region code, for out_of_region_use detection


class Edge(BaseModel):
    src: str
    dst: str
    type: str  # SHARES_DEVICE | SHARES_EMAIL | SHARES_ADDRESS | OWNS | MADE


class AccountSubgraphInput(BaseModel):
    account_id: str
    as_of: str | None = None
    card_id: str | None = None


class AccountSubgraphOutput(BaseModel):
    accounts: list[str]
    transactions: list[TxnSummary]
    cards: list[str]
    devices: list[str]
    emails: list[str]
    addresses: list[str]
    edges: list[Edge]


class FraudRingInput(BaseModel):
    account_id: str
    as_of: str | None = None
    card_id: str | None = None


class FraudRingOutput(BaseModel):
    ring_id: str
    size: int
    members: list[str]
    known_fraud_count: int
    shared_via: list[str]  # e.g. ["SHARES_DEVICE", "SHARES_ADDRESS"]


class TransactionVelocityInput(BaseModel):
    account_id: str
    window_hours: float
    as_of: str | None = None
    card_id: str | None = None


class TransactionVelocityOutput(BaseModel):
    count: int
    sum_amount: float
    max_amount: float
    z_score: float
    baseline_mean: float
    baseline_std: float


class PriorSimilarCasesInput(BaseModel):
    case_text: str
    k: int = 5
    as_of: str | None = None


class SimilarCase(BaseModel):
    case_id: str
    similarity: float
    outcome: str
    pattern: str


class PriorSimilarCasesOutput(BaseModel):
    results: list[SimilarCase]


class PolicyContextInput(BaseModel):
    topic: str


class PolicyClause(BaseModel):
    clause_id: str
    text: str


class PolicyContextOutput(BaseModel):
    clauses: list[PolicyClause]


class Typology(BaseModel):
    typology_id: str
    name: str
    indicators: str


class TypologiesOutput(BaseModel):
    typologies: list[Typology]


class FindOpenCaseInput(BaseModel):
    entity_id: str


class FindOpenCaseOutput(BaseModel):
    found: bool
    case_id: str | None = None


class WriteCaseInput(BaseModel):
    case_id: str
    case_json: str  # serialized CaseRecord
    opened_at: str | None = None  # the case's real trigger time, not wall-clock - needed so a
    # later case can legitimately find this one as a similar prior case without future leakage


class WriteCaseOutput(BaseModel):
    written: bool
    graph_case_id: str
    similar_to: list[str] = Field(default_factory=list)


def export_schemas(out_dir: str = "contracts") -> None:
    import json
    from pathlib import Path

    models = {
        "tool_account_subgraph": (AccountSubgraphInput, AccountSubgraphOutput),
        "tool_fraud_ring": (FraudRingInput, FraudRingOutput),
        "tool_transaction_velocity": (TransactionVelocityInput, TransactionVelocityOutput),
        "tool_prior_similar_cases": (PriorSimilarCasesInput, PriorSimilarCasesOutput),
        "tool_policy_context": (PolicyContextInput, PolicyContextOutput),
        "tool_typologies": (None, TypologiesOutput),
        "tool_find_open_case": (FindOpenCaseInput, FindOpenCaseOutput),
        "tool_write_case": (WriteCaseInput, WriteCaseOutput),
    }
    out = Path(out_dir)
    for name, (in_model, out_model) in models.items():
        schema = {"input": in_model.model_json_schema() if in_model else None, "output": out_model.model_json_schema()}
        (out / f"{name}_schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")


if __name__ == "__main__":
    export_schemas()
    print("wrote tool_*_schema.json to contracts/")
