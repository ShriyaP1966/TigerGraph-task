"""Adapter over P1's graph/mcp/tools.py (a plain importable Python module, not a
running MCP server - graph/ is P1's work, landed inside this repo). Every method
tries the real call first and falls back to LocalBackend per-call (not all-or-
nothing) on any failure - which, as of this writing, is every call: no TigerGraph
Docker CE or Savanna instance is reachable (checked: ports 14240/9000 both refused,
Docker daemon isn't running, no TG_* env vars point anywhere). P1's own graph/README.md
documents the same status.

P1's tools are CARD-keyed (card_id like "C01234-K1"); this backend's interface is
ACCOUNT-keyed (customer_id), matching the rest of the system. _resolve_card_id
bridges that using LocalBackend's own card synthesis when the agent doesn't already
have the real card_id (it does, for the case's own account, via the card_id hint).

Several of P1's tools don't expose everything this backend's contract needs - those
gaps are filled from self._local (documented per method below), which is a
deliberate hybrid, not a bug: P1's graph is the source of truth for what it does
expose (topology, transactions, policy), Local fills in what P1's tools don't
compute yet (known_fraud_count, velocity baseline/z-score, as_of filtering on
similar-case retrieval).
"""
import json
import logging

from backends.base import GraphBackend
from backends.local import LocalBackend
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

logger = logging.getLogger(__name__)

SHARED_TYPE_TO_EDGE = {"device": "SHARES_DEVICE", "email_domain": "SHARES_EMAIL", "billing_region": "SHARES_ADDRESS"}


def _apply_short_timeout(conn, seconds: float = 3.0) -> None:
    """pyTigerGraph passes timeout=None to requests whenever no GSQL-TIMEOUT header is
    set, which disables any client-side timeout entirely - a genuinely unreachable host
    (as opposed to an actively-refused one) would hang indefinitely rather than fail
    fast. Patches this connection's own session, not the global socket default, so it
    can't affect unrelated calls elsewhere in the process (e.g. live Groq/Gemini calls,
    which routinely take 10-30s and would break under a global short timeout)."""
    sess = conn._session
    orig_request = sess.request

    def _request_with_timeout(method, url, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = seconds
        return orig_request(method, url, **kwargs)

    sess.request = _request_with_timeout


def _import_p1_tools():
    import os

    # config.py's TG_REST_PORT default (9000) is TigerGraph's pre-4.x REST port; this
    # stack is 4.x (RESTPP moved to 14240), so every call burned a full connection
    # attempt on the wrong port before pyTigerGraph's own port-fallback logic retried
    # on the right one - doubling latency. TG_HOST's default "localhost" costs a second
    # wasted attempt per call too, from Windows trying the IPv6 loopback (::1) before
    # falling back to IPv4 - resolving straight to 127.0.0.1 skips that. Measured:
    # ~8.1s/call (localhost, wrong port first) -> ~4.1s (right port, localhost) -> ~2.1s
    # (right port, explicit IPv4). Only applied if not already set, so a real TG_HOST
    # (e.g. a Savanna cloud URL) is never overridden.
    os.environ.setdefault("TG_REST_PORT", "14240")
    os.environ.setdefault("TG_HOST", "http://127.0.0.1")

    import graph.mcp.config as p1_config
    import graph.mcp.tools as p1_tools

    # config.py's module-level constants are read from os.environ once at first import,
    # so if graph.mcp.config was already imported elsewhere in this process before the
    # setdefault above ran, refresh them directly rather than relying on a re-import.
    p1_config.TG_REST_PORT = int(os.environ["TG_REST_PORT"])
    p1_config.TG_HOST = os.environ["TG_HOST"]

    p1_config.MCP_MODE = "live"  # force a real connection attempt - fixture mode returns the
    # same canned HHG-001 response regardless of which case is asked about, which would make
    # a per-case TigerGraph-vs-Local diff meaningless

    _apply_short_timeout(p1_tools._get_connection())
    return p1_tools


class TigerGraphBackend(GraphBackend):
    def __init__(self):
        self._local = LocalBackend()  # fallback for any call that fails, plus fills gaps P1's tools don't cover
        try:
            self._p1 = _import_p1_tools()
        except Exception as e:
            logger.warning("could not import P1's graph/mcp/tools.py (%s) - every call will fall back to local", e)
            self._p1 = None

    def _resolve_card_id(self, account_id: str, as_of: str | None, card_id: str | None) -> str:
        if card_id:
            return card_id
        sg = self._local.get_account_subgraph(account_id, as_of=as_of)
        return sg.cards[0] if sg.cards else f"{account_id}-K1"

    def get_account_subgraph(self, account_id: str, as_of: str | None = None, card_id: str | None = None) -> AccountSubgraphOutput:
        try:
            if self._p1 is None:
                raise RuntimeError("P1 tools not importable")
            card = self._resolve_card_id(account_id, as_of, card_id)
            r = self._p1.get_account_subgraph(card, txn_limit=300, include_shared_links=True)

            txns = [
                TxnSummary(
                    txn_id=t["txn_id"], ts=t["ts"], amount=t["amount"], product_cd=t["product_cd"],
                    channel=t["channel"], risk_score=t.get("risk_score"), card_id=card,
                    device_new=None,  # P1's Transaction vertex has no id_15/"New device" equivalent - real capability gap, not a conversion bug
                    addr1=t.get("addr1"),
                )
                for t in r["transactions"]
            ]
            edges = [
                # dst is approximated as customer_id by stripping "-K<n>" from the linked card_id (same
                # naming convention this system uses everywhere) - P1's shared_links only gives card_id, not customer_id
                Edge(src=account_id, dst=link["linked_card_id"].split("-K")[0], type=link["link_type"])
                for link in r.get("shared_links", [])
            ]
            return AccountSubgraphOutput(
                accounts=[account_id],
                transactions=txns,
                cards=[r["card"]["card_id"]],
                devices=sorted({t["device_id"] for t in r["transactions"] if t.get("device_id")}),
                emails=sorted({t["p_email_domain"] for t in r["transactions"] if t.get("p_email_domain")}),
                addresses=sorted({t["addr1"] for t in r["transactions"] if t.get("addr1")}),
                edges=edges,
            )
        except Exception as e:
            logger.warning("tigergraph get_account_subgraph failed (%s), falling back to local", e)
            return self._local.get_account_subgraph(account_id, as_of, card_id)

    def find_fraud_ring(self, account_id: str, as_of: str | None = None, card_id: str | None = None) -> FraudRingOutput:
        try:
            if self._p1 is None:
                raise RuntimeError("P1 tools not importable")
            card = self._resolve_card_id(account_id, as_of, card_id)
            r = self._p1.find_fraud_ring(card, max_hops=2, min_shared_weight=1)

            members = sorted({c["customer_id"] for c in r["cards"] if c.get("customer_id")})
            shared_via = sorted({SHARED_TYPE_TO_EDGE.get(a["type"], a["type"]) for a in r["shared_attributes"]})
            # P1's find_fraud_ring doesn't return known-fraud density at all (no such field in
            # the published contract) - cross-referenced locally against the same
            # closed_cases_history.csv every backend loads, not a fabricated number
            known_fraud = sum(1 for m in members if m in self._local._confirmed_fraud_accounts)

            return FraudRingOutput(ring_id=r["cluster_id"], size=len(members) or 1, members=members or [account_id], known_fraud_count=known_fraud, shared_via=shared_via)
        except Exception as e:
            logger.warning("tigergraph find_fraud_ring failed (%s), falling back to local", e)
            return self._local.find_fraud_ring(account_id, as_of, card_id)

    def get_transaction_velocity(self, account_id: str, window_hours: float, as_of: str | None = None, card_id: str | None = None) -> TransactionVelocityOutput:
        try:
            if self._p1 is None:
                raise RuntimeError("P1 tools not importable")
            card = self._resolve_card_id(account_id, as_of, card_id)
            # P1's tool takes window_minutes and a reference_txn_id (not an as_of timestamp) -
            # with no txn id available at this call site, this always anchors to the card's
            # latest transaction rather than the case's as_of cutoff, a real (documented) gap
            r = self._p1.get_transaction_velocity(card, window_minutes=int(window_hours * 60), reference_txn_id="", amount_threshold=5.0)

            # P1's velocity tool returns no baseline/z-score at all - filled from local, which
            # already has the full transaction history in memory for this
            local_baseline = self._local.get_transaction_velocity(account_id, window_hours, as_of, card_id)

            return TransactionVelocityOutput(
                count=r["txn_count"], sum_amount=r["txn_sum"],
                max_amount=local_baseline.max_amount, z_score=local_baseline.z_score,
                baseline_mean=local_baseline.baseline_mean, baseline_std=local_baseline.baseline_std,
            )
        except Exception as e:
            logger.warning("tigergraph get_transaction_velocity failed (%s), falling back to local", e)
            return self._local.get_transaction_velocity(account_id, window_hours, as_of, card_id)

    def get_prior_similar_cases(self, case_text: str, k: int = 5, as_of: str | None = None) -> PriorSimilarCasesOutput:
        try:
            if self._p1 is None:
                raise RuntimeError("P1 tools not importable")
            # P1's get_prior_similar_cases has no as_of/time filter at all (not in the published
            # contract) - can't honor no-future-leakage yet. Not exploitable today since nothing
            # is live, but flagged here for whoever wires this up once TigerGraph is up.
            r = self._p1.get_prior_similar_cases(query_text=case_text, top_k=k)
            results = [SimilarCase(case_id=c["case_id"], similarity=c["similarity_score"], outcome=c["outcome"], pattern=c["pattern"]) for c in r["similar_cases"]]
            return PriorSimilarCasesOutput(results=results)
        except Exception as e:
            logger.warning("tigergraph get_prior_similar_cases failed (%s), falling back to local", e)
            return self._local.get_prior_similar_cases(case_text, k, as_of)

    def get_policy_context(self, topic: str) -> list[PolicyClause]:
        try:
            if self._p1 is None:
                raise RuntimeError("P1 tools not importable")
            r = self._p1.get_policy_context(topic)
            return [PolicyClause(clause_id=c["clause_id"], text=c["text"]) for c in r["policy_clauses"]]
        except Exception as e:
            logger.warning("tigergraph get_policy_context failed (%s), falling back to local", e)
            return self._local.get_policy_context(topic)

    def get_typologies(self) -> list[Typology]:
        try:
            if self._p1 is None:
                raise RuntimeError("P1 tools not importable")
            # P1 has no standalone typologies tool - typologies ride along in get_policy_context's
            # response, so call that (empty topic = no filter) and take just the typologies half
            r = self._p1.get_policy_context("")
            return [Typology(typology_id=t["typology_id"], name=t["typology_id"].replace("_", " "), indicators=t["description"]) for t in r["typologies"]]
        except Exception as e:
            logger.warning("tigergraph get_typologies failed (%s), falling back to local", e)
            return self._local.get_typologies()

    def find_open_case(self, entity_id: str) -> str | None:
        # P1 has published no equivalent tool at all - always local, not a failure-triggered fallback
        return self._local.find_open_case(entity_id)

    def write_case(self, case_id: str, case_json: str, opened_at: str | None = None) -> WriteCaseOutput:
        parsed = json.loads(case_json)
        # always write to local memory too, for two reasons: (1) P1's write_case_to_graph
        # returns similar_to_edges_created as a COUNT, not the case IDs this contract's
        # similar_to expects, so local gives us real IDs; (2) it keeps case-memory demo/
        # tuning scripts working the same way regardless of which graph backend is active
        c = parsed.get("case", {})
        text = c.get("summary", "") + " " + " ".join(e.get("claim", "") for e in c.get("evidence", []))
        outcome = {"fraud": "confirmed_fraud", "legitimate": "cleared", "uncertain": "uncertain"}.get(c.get("verdict"), "uncertain")
        local_links = self._local.memory.add_case(case_id, text, outcome, c.get("pattern", "none"), opened_at=opened_at or "")

        try:
            if self._p1 is None:
                raise RuntimeError("P1 tools not importable")
            r = self._p1.write_case_to_graph(case_id=case_id, case=parsed["case"], next_best_actions=parsed["next_best_actions"], sar=parsed.get("sar"))
            return WriteCaseOutput(written=r["written"], graph_case_id=r["graph_case_id"], similar_to=local_links)
        except Exception as e:
            logger.warning("tigergraph write_case failed (%s), falling back to local", e)
            return WriteCaseOutput(written=True, graph_case_id=f"LOCAL-{case_id}", similar_to=local_links)
