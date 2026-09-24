import json
import statistics
from datetime import datetime
from pathlib import Path

from backends.base import GraphBackend
from contracts.tool_contracts import (
    AccountSubgraphOutput,
    Edge,
    FraudRingOutput,
    PolicyClause,
    PriorSimilarCasesOutput,
    SimilarCase,
    TransactionVelocityOutput,
    Typology,
    TxnSummary,
    WriteCaseOutput,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class MockBackend(GraphBackend):
    def __init__(self):
        self.accounts = json.loads((FIXTURES_DIR / "accounts.json").read_text())
        self.rings = json.loads((FIXTURES_DIR / "rings.json").read_text())
        self.prior_cases = json.loads((FIXTURES_DIR / "prior_cases.json").read_text())
        pt = json.loads((FIXTURES_DIR / "policy_typologies.json").read_text())
        self.policy_clauses = pt["policy_clauses"]
        self.typologies = pt["typologies"]
        self._written_cases: dict[str, str] = {}

    def _account(self, account_id: str) -> dict:
        return self.accounts.get(account_id, {"cards": [], "devices": [], "emails": [], "addresses": [], "transactions": [], "edges": []})

    def get_account_subgraph(self, account_id: str, as_of: str | None = None, card_id: str | None = None) -> AccountSubgraphOutput:
        a = self._account(account_id)
        txns = a["transactions"]
        if as_of:
            txns = [t for t in txns if t["ts"] <= as_of]
        return AccountSubgraphOutput(
            accounts=[account_id],
            transactions=[TxnSummary(**t) for t in txns],
            cards=a["cards"],
            devices=a["devices"],
            emails=a["emails"],
            addresses=a["addresses"],
            edges=[Edge(**e) for e in a["edges"]],
        )

    def find_fraud_ring(self, account_id: str, as_of: str | None = None, card_id: str | None = None) -> FraudRingOutput:
        r = self.rings.get(account_id, {"ring_id": "", "size": 1, "members": [account_id], "known_fraud_count": 0, "shared_via": []})
        return FraudRingOutput(**r)

    def get_transaction_velocity(self, account_id: str, window_hours: float, as_of: str | None = None, card_id: str | None = None) -> TransactionVelocityOutput:
        a = self._account(account_id)
        txns = a["transactions"]
        if as_of:
            txns = [t for t in txns if t["ts"] <= as_of]
        if not txns:
            return TransactionVelocityOutput(count=0, sum_amount=0, max_amount=0, z_score=0, baseline_mean=0, baseline_std=0)

        cutoff_ts = as_of or txns[-1]["ts"]
        cutoff = datetime.fromisoformat(cutoff_ts.replace("Z", "+00:00"))
        window = [t for t in txns if (cutoff - datetime.fromisoformat(t["ts"].replace("Z", "+00:00"))).total_seconds() <= window_hours * 3600]

        amounts = [t["amount"] for t in txns]
        mean = statistics.mean(amounts)
        std = statistics.pstdev(amounts) or 1.0
        window_sum = sum(t["amount"] for t in window)
        z = (window_sum - mean) / std

        return TransactionVelocityOutput(
            count=len(window),
            sum_amount=window_sum,
            max_amount=max((t["amount"] for t in window), default=0),
            z_score=z,
            baseline_mean=mean,
            baseline_std=std,
        )

    def get_prior_similar_cases(self, case_text: str, k: int = 5, as_of: str | None = None) -> PriorSimilarCasesOutput:
        words = set(case_text.lower().split())
        scored = []
        for c in self.prior_cases:
            cwords = set(c["text"].lower().split())
            overlap = len(words & cwords) / max(len(words | cwords), 1)
            scored.append((overlap, c))
        scored.sort(key=lambda x: -x[0])
        results = [
            SimilarCase(case_id=c["case_id"], similarity=round(score, 3), outcome=c["outcome"], pattern=c["pattern"])
            for score, c in scored[:k]
        ]
        return PriorSimilarCasesOutput(results=results)

    def get_policy_context(self, topic: str) -> list[PolicyClause]:
        return [PolicyClause(**c) for c in self.policy_clauses]

    def get_typologies(self) -> list[Typology]:
        return [Typology(**t) for t in self.typologies]

    def find_open_case(self, entity_id: str) -> str | None:
        return self._written_cases.get(entity_id)

    def write_case(self, case_id: str, case_json: str, opened_at: str | None = None) -> WriteCaseOutput:
        self._written_cases[case_id] = case_json
        return WriteCaseOutput(written=True, graph_case_id=f"MOCK-{case_id}", similar_to=[])
