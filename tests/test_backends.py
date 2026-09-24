"""Same checks against every GraphBackend implementation. If P1's TigerGraphBackend
fails one of these, that's the contract being violated, not a bug in the test."""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backends.mock import MockBackend
from contracts.tool_contracts import (
    AccountSubgraphOutput,
    FraudRingOutput,
    PolicyClause,
    PriorSimilarCasesOutput,
    TransactionVelocityOutput,
    Typology,
    WriteCaseOutput,
)

BACKENDS = [("mock", MockBackend, "ACCT-RING-1")]

try:
    from backends.local import LocalBackend

    BACKENDS.append(("local", LocalBackend, "C08623"))
except Exception as e:  # pragma: no cover - only hit if data/transactions.csv isn't set up yet
    print(f"skipping local backend contract test: {e}")

try:
    from backends.tigergraph import TigerGraphBackend

    BACKENDS.append(("tigergraph", TigerGraphBackend, "C08623"))
except Exception as e:  # pragma: no cover
    print(f"skipping tigergraph backend contract test: {e}")


@pytest.mark.parametrize("name,cls,account_id", BACKENDS, ids=[b[0] for b in BACKENDS])
def test_backend_contract(name, cls, account_id):
    backend = cls()

    sg = backend.get_account_subgraph(account_id)
    assert isinstance(sg, AccountSubgraphOutput)
    assert account_id in sg.accounts

    ring = backend.find_fraud_ring(account_id)
    assert isinstance(ring, FraudRingOutput)
    assert ring.size >= 1
    assert account_id in ring.members

    vel = backend.get_transaction_velocity(account_id, window_hours=24)
    assert isinstance(vel, TransactionVelocityOutput)
    assert vel.count >= 0

    sim = backend.get_prior_similar_cases("card testing burst then a larger purchase", k=3)
    assert isinstance(sim, PriorSimilarCasesOutput)
    assert len(sim.results) <= 3
    for r in sim.results:
        assert 0 <= r.similarity <= 1

    clauses = backend.get_policy_context("card testing")
    assert all(isinstance(c, PolicyClause) for c in clauses)
    assert len(clauses) > 0

    typologies = backend.get_typologies()
    assert all(isinstance(t, Typology) for t in typologies)
    assert len(typologies) >= 3

    result = backend.write_case("TEST-CONTRACT-001", '{"case": {"summary": "test", "evidence": [], "verdict": "uncertain", "pattern": "none"}}')
    assert isinstance(result, WriteCaseOutput)
    assert result.written


if __name__ == "__main__":
    for name, cls, account_id in BACKENDS:
        test_backend_contract(name, cls, account_id)
        print(f"[PASS] {name} backend contract")
