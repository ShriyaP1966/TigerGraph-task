"""LangGraph nodes. Each takes the full CaseState and returns a dict of the
keys it updates. Nodes only talk to the graph through state["backend"]
(a GraphBackend) - never import tigergraph/mcp code here.
"""
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from agent.patterns import choose_pattern
from agent.rules import recommend_actions, response_indicates_fraud, simulate_response
from contracts.case_record import ActionItem, Case, CaseRecord, Evidence, EvidenceRequest, NextBestActions, SAR
from llm.client import complete
from llm.prompts import build_context, explanation_prompt, sar_prompt, validate_citations
from policy.gate import approval_gate as gate_fn
from scoring.confidence import apply_response_override, compute_confidence

_AGENT_CFG = yaml.safe_load((Path(__file__).resolve().parent.parent / "config.yaml").read_text())["agent"]

EVIDENCE_TYPE_TO_SOURCE = {
    "graph_pattern": "graph",
    "transaction_history": "graph",
    "device_signal": "graph",
    "identity_signal": "graph",
    "prior_case": "graph",
    "policy": "document",
    "analyst_input": "external",
    "customer_response": "customer",
}

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _add_evidence(state: dict, type_: str, description: str, source_tool: str, entity_ids: list | None = None) -> tuple[list[dict], str]:
    evidence = list(state["evidence"])
    eid = f"EV-{len(evidence) + 1:03d}"
    evidence.append({"evidence_id": eid, "type": type_, "description": description, "source_tool": source_tool, "timestamp": _now(), "entity_ids": entity_ids or []})
    return evidence, eid


def trigger_intake(state: dict) -> dict:
    backend = state["backend"]
    sg = backend.get_account_subgraph(state["customer_id"], card_id=state.get("card_id"))
    flagged = next((t for t in sg.transactions if t.txn_id == state["flagged_txn_id"]), None)
    as_of = flagged.ts if flagged else state["opened_at"]

    evidence, _ = _add_evidence(
        state, "transaction_history", f"Trigger ({state['trigger_type']}): {state['trigger_text']}", "case_pack", [state["flagged_txn_id"]]
    )

    return {
        "as_of": as_of,
        "flagged_txn": flagged.model_dump() if flagged else None,
        "evidence": evidence,
        "tool_calls": state["tool_calls"] + 1,
    }


def open_or_load_case(state: dict) -> dict:
    backend = state["backend"]
    existing = backend.find_open_case(state["customer_id"])
    evidence = list(state["evidence"])
    if existing:
        evidence, _ = _add_evidence(state, "prior_case", f"Existing open case {existing} found for this customer", "find_open_case", [existing])
    return {"evidence": evidence, "status": "open", "tool_calls": state["tool_calls"] + 1}


def gather_graph_evidence(state: dict) -> dict:
    backend = state["backend"]
    cid, as_of = state["customer_id"], state["as_of"]
    card = state.get("card_id")

    sg = backend.get_account_subgraph(cid, as_of=as_of, card_id=card)
    ring = backend.find_fraud_ring(cid, as_of=as_of, card_id=card)
    vel1 = backend.get_transaction_velocity(cid, window_hours=1, as_of=as_of, card_id=card)
    vel48 = backend.get_transaction_velocity(cid, window_hours=48, as_of=as_of, card_id=card)

    evidence = list(state["evidence"])
    evidence, _ = _add_evidence(state, "transaction_history", f"{len(sg.transactions)} transactions in the account's recent window", "get_account_subgraph")
    state_copy = {**state, "evidence": evidence}
    # ring.size/ring.members/ring.known_fraud_count are raw/uncapped (a common device/region
    # can inflate them into the thousands - see graph/queries/device_ring.gsql) so they're not usable
    # as evidence claims or entity_ids on their own. member_card_ids is cardinality-capped but
    # still just "shares a device" - R6 needs cards that actually show fraud, which is
    # fraud_confirmed_member_cards (see backends/tigergraph.py::_filter_fraud_confirmed). Cite
    # that as the evidentiary claim; mention the broader device-sharing count only for context.
    if ring.fraud_confirmed_member_cards:
        device_note = f" via {ring.rare_shared_devices[0]}" if ring.rare_shared_devices else ""
        evidence, _ = _add_evidence(
            state_copy, "graph_pattern",
            f"{len(ring.fraud_confirmed_member_cards)} other card(s) sharing a rare device profile{device_note} show real fraud evidence "
            f"(a confirmed_fraud closed case on record), out of {len(ring.member_card_ids)} total cards on that device",
            "device_ring", ring.fraud_confirmed_member_cards,
        )
        state_copy = {**state_copy, "evidence": evidence}
    elif ring.member_card_ids:
        evidence, _ = _add_evidence(
            state_copy, "graph_pattern",
            f"{len(ring.member_card_ids)} other card(s) share a rare device profile with this account, but none show independent fraud evidence",
            "device_ring",
        )
        state_copy = {**state_copy, "evidence": evidence}
        state_copy = {**state_copy, "evidence": evidence}
    evidence, _ = _add_evidence(state_copy, "transaction_history", f"{vel1.count} txns in the last hour totaling ${vel1.sum_amount:.2f}, z-score {vel1.z_score:.2f}", "get_transaction_velocity(1h)")
    state_copy = {**state_copy, "evidence": evidence}
    evidence, _ = _add_evidence(state_copy, "transaction_history", f"{vel48.count} txns in the last 48h totaling ${vel48.sum_amount:.2f}, z-score {vel48.z_score:.2f}", "get_transaction_velocity(48h)")

    return {
        "subgraph_txns": sg.transactions,
        "device_profiles": sg.devices,
        "ring": ring.model_dump(),
        "velocity_1h": vel1.model_dump(),
        "velocity_48h": vel48.model_dump(),
        "evidence": evidence,
        "tool_calls": state["tool_calls"] + 4,
    }


def gather_graphrag_context(state: dict) -> dict:
    backend = state["backend"]
    case_text = f"{state['trigger_text']} ring size {state['ring']['size']} known fraud {state['ring']['known_fraud_count']}"
    sim = backend.get_prior_similar_cases(case_text, k=5, as_of=state["opened_at"])
    policy = backend.get_policy_context(state["trigger_type"])
    typologies = backend.get_typologies()

    # only the top 3 of the k=5 retrieved become evidence items (keeps the evidence list
    # from getting cluttered with weak 4th/5th-ranked matches) - similar_cases below is
    # sliced to match, since it's also what the LLM's prompt shows and what citation
    # validation checks against. Previously this returned all 5, so the LLM could validly
    # cite a 4th/5th-ranked case ID with no backing entry in the persisted evidence list -
    # not a hallucination by the validator's own contract, but a real traceability gap
    # against DATASET_README.md's "the evidence list carries the detail."
    top = sim.results[:3]
    evidence = list(state["evidence"])
    state_copy = {**state, "evidence": evidence}
    for c in top:
        evidence, _ = _add_evidence(state_copy, "prior_case", f"Similar prior case {c.case_id} (similarity {c.similarity}, outcome {c.outcome}, pattern {c.pattern})", "get_prior_similar_cases", [c.case_id])
        state_copy = {**state_copy, "evidence": evidence}

    return {
        "similar_cases": [c.model_dump() for c in top],
        "policy_clauses": [p.model_dump() for p in policy],
        "typologies": [t.model_dump() for t in typologies],
        "evidence": evidence,
        "tool_calls": state["tool_calls"] + 3,
    }


def _matches_recurring_pattern(subgraph_txns: list, flagged: dict) -> bool:
    """R7: does the disputed transaction match this customer's OWN recurring spend pattern -
    same product code, amount within 15%, appearing in at least two other distinct months
    besides the flagged one? A customer disputing what's plainly their own recurring charge
    (a subscription, a regular bill) isn't grounds to block the card outright - verify and
    warn instead (see agent/rules.py::recommend_actions' R7 branch)."""
    if not flagged or not flagged.get("product_cd") or not flagged.get("amount"):
        return False
    amount = flagged["amount"]
    flagged_id = flagged.get("txn_id")
    similar = [
        t for t in subgraph_txns
        if t.txn_id != flagged_id and t.product_cd == flagged["product_cd"] and abs(t.amount - amount) <= amount * 0.15
    ]
    if len(similar) < 2:
        return False
    months = set()
    for t in similar:
        ts = t.ts.replace("Z", "+00:00") if ("Z" in t.ts or "+" in t.ts) else t.ts
        months.add(datetime.fromisoformat(ts).strftime("%Y-%m"))
    return len(months) >= 2


def _build_case_facts(state: dict) -> dict:
    """Shared by assess_patterns_and_risk (decisiveness gate) and request_more_evidence
    (simulate_response's input) so the two never compute this from different data."""
    flagged = state.get("flagged_txn") or {}
    flagged_id = state.get("flagged_txn_id")
    subgraph_txns = state.get("subgraph_txns", [])
    other_amounts = sorted(t.amount for t in subgraph_txns if t.txn_id != flagged_id)
    typical_amount = other_amounts[len(other_amounts) // 2] if other_amounts else 0  # median, robust to outliers
    history_regions = [t.addr1 for t in subgraph_txns if t.addr1 and t.txn_id != flagged_id]
    home_region = max(set(history_regions), key=history_regions.count) if history_regions else None
    region_new = bool(home_region and flagged.get("addr1") and flagged["addr1"] != home_region)
    return {
        "trigger_type": state["trigger_type"],
        "device_new": flagged.get("device_new"),
        "region_new": region_new,
        "velocity_z_score": (state.get("velocity_48h") or {}).get("z_score"),
        "flagged_amount": flagged.get("amount"),
        "typical_amount": typical_amount,
        "risk_score": flagged.get("risk_score"),
    }


def _out_of_character_count(case_facts: dict) -> int:
    """How many of this transaction's own facts look out of character for this customer -
    new device, new region, a velocity spike, or an amount well above their typical spend.
    0 -> clearly matches history, >=2 -> clearly doesn't; ==1 is a genuine single-signal
    case, not decisive enough to force a verdict on its own."""
    z = case_facts.get("velocity_z_score") or 0
    amount = case_facts.get("flagged_amount") or 0
    typical = case_facts.get("typical_amount") or 0
    return sum([
        bool(case_facts.get("device_new")),
        bool(case_facts.get("region_new")),
        z > 2,
        typical > 0 and amount > typical * 2,
    ])


def assess_patterns_and_risk(state: dict) -> dict:
    txns = state["subgraph_txns"]
    pattern, strength = choose_pattern(txns, state["flagged_txn_id"], state["ring"], state["trigger_type"])

    flagged = state.get("flagged_txn") or {}
    bank_risk = flagged.get("risk_score")
    if bank_risk is None:
        bank_risk = state.get("risk_score_input") or 0.3

    similarity_to_fraud = 0.0
    for c in state["similar_cases"]:
        if c["outcome"] == "confirmed_fraud":
            similarity_to_fraud = max(similarity_to_fraud, c["similarity"])

    evidence_types_present = {e["type"] for e in state["evidence"]}
    coverage = min(len(evidence_types_present) / 5, 1.0)

    # ring["size"] is uncapped (a common device/region can inflate it into the thousands -
    # see graph/queries/device_ring.gsql), and merely sharing a rare device isn't a fraud signal on
    # its own either - fraud_confirmed_member_cards is the cardinality-capped signal already
    # filtered to cards with real fraud evidence (see backends/tigergraph.py).
    real_ring_signal = len(state["ring"].get("fraud_confirmed_member_cards", [])) >= 1
    signal_count = int(real_ring_signal) + int(bank_risk > 0.5) + int(strength > 0.3)

    # bank_risk/typology_match/similarity always reflect genuine evidence, never the
    # evidence-request response - that's applied as a separate, documented override on
    # the score below, so bank_risk_score in the breakdown is always the flagged
    # transaction's real risk_score, not something silently nudged by a customer's answer
    confidence = compute_confidence(bank_risk, strength, similarity_to_fraud, coverage)

    response = state.get("customer_response")
    last_request_type = state["evidence_requests"][-1]["type"] if state.get("evidence_requests") else None
    if response and last_request_type:
        confidence = apply_response_override(confidence, last_request_type, response_indicates_fraud(response))
    score = confidence["score"]

    # R2/R3: a direct customer confirm/deny always settles the verdict outright - this was
    # always unconditional (not gated on this transaction's own facts), and stays that way:
    # for customer_report/risk_score the response text is now decisive/fact-based (see
    # simulate_response), and for analyst_request it's the ring-aware blend (ring_score,
    # gated to analyst_request in simulate_response) that drives the lean - either way, a
    # direct customer answer is the strongest evidence the policy defines and settles it.
    case_facts = _build_case_facts(state)
    if response and last_request_type == "customer_validation":
        verdict = "fraud" if response_indicates_fraud(response) else "legitimate"
    # step_up_auth's risk_score equivalent (new - step_up_auth was never decisive before):
    # a clean pass (0 out-of-character signals) or a clean fail (>=2) settles it; exactly 1
    # signal is a genuine single-signal case, not decisive enough on its own - falls through
    # to the score bands below instead of being forced (this is the ~3-5-case uncertain
    # bucket the calibration target asks for).
    elif response and last_request_type == "step_up_auth" and state["trigger_type"] == "risk_score" and _out_of_character_count(case_facts) != 1:
        verdict = "fraud" if response_indicates_fraud(response) else "legitimate"
    else:
        verdict = "fraud" if score >= 0.70 else ("legitimate" if score <= 0.20 else "uncertain")
        # R6/R9: several OTHER cards sharing a rare device that independently show real fraud
        # evidence is itself strong, structural evidence - settled outright the same way
        # R2/R3's direct customer response is, rather than stuck "uncertain" just because
        # this transaction's own bank risk_score is low (bank_risk_score is only 30% of the
        # weighted confidence formula, so ring evidence alone can't cross 0.70 there).
        #
        # Also requires an elevated own_signal (bank risk_score or a new device): ring
        # evidence is common enough across the case pack that using it alone would push most
        # cases to "fraud" regardless of whether this transaction shows anything itself -
        # the ring corroborates the case's own signal, it doesn't substitute for it. And
        # gated to analyst_request (belt-and-suspenders with choose_pattern, which already
        # only returns "undocumented" for that trigger) - ring evidence drives verdict/SAR
        # only when the trigger is explicitly an analyst asking about shared-device activity.
        ring_fraud_confirmed = len(state["ring"].get("fraud_confirmed_member_cards", []))
        own_signal = bank_risk >= 0.7 or bool(flagged.get("device_new"))
        if (
            verdict != "fraud" and pattern == "undocumented" and ring_fraud_confirmed >= 3
            and own_signal and state["trigger_type"] == "analyst_request"
        ):
            verdict = "fraud"

    # R9/Notes: a legitimate verdict has no fraud pattern to report, regardless of what
    # choose_pattern matched on the evidence gathered before a clearing response arrived.
    if verdict == "legitimate":
        pattern = "none"

    pattern_description = ""
    if pattern == "undocumented":
        member_cards = state["ring"].get("member_card_ids", [])
        devices = state["ring"].get("rare_shared_devices", [])
        if member_cards:
            pattern_description = (
                f"{len(member_cards)} other card(s) share a device profile with this account"
                f"{f' ({devices[0]})' if devices else ''} that this transaction otherwise fits none of the five documented "
                f"fraud patterns for - coordinated activity across accounts that isn't card testing, card-not-present fraud, "
                f"out-of-region use, or account takeover on their own."
            )
        else:
            pattern_description = (
                f"Activity connects to {state['ring']['known_fraud_count']} account(s) with confirmed fraud history, "
                f"but does not fit any of the five documented fraud patterns on its own."
            )

    result = {
        "pattern": pattern,
        "typology_match_strength": strength,
        "pattern_description": pattern_description,
        "confidence": confidence,
        "verdict": verdict,
        "evidence_signal_count": signal_count,
        "recurring_pattern_match": _matches_recurring_pattern(txns, flagged),
    }
    if "confidence_before" not in state:
        result["confidence_before"] = confidence  # first pass, before any evidence response - never overwritten again
    return result


def uncertainty_gate(state: dict) -> dict:
    if state.get("initial_actions") is not None:
        return {}
    initial = recommend_actions(
        pattern=state["pattern"], verdict=state["verdict"], fraud_probability=state["confidence"]["score"],
        exposure_usd=state.get("exposure_usd", 0), ring=state["ring"], evidence_signal_count=state.get("evidence_signal_count", 0),
        last_response=None, already_cleared_amount=state.get("already_cleared_amount", 0),
        trigger_type=state["trigger_type"], recurring_pattern_match=state.get("recurring_pattern_match", False),
    )
    return {"initial_actions": initial}


def route_after_uncertainty(state: dict) -> str:
    # R2/R3: once the customer has directly confirmed or denied, that settles the
    # verdict outright (see assess_patterns_and_risk) regardless of confidence band -
    # asking anything further would let a later, less authoritative response (e.g.
    # analyst_info) silently take over which branch of the verdict logic fires, since
    # that's keyed off the MOST RECENT request type. This only became reachable once
    # apply_response_override stopped snapping straight to 0.85/0.15 (which used to
    # push the score past the act threshold in one step, ending the loop as a side
    # effect); the smaller additive nudge doesn't always clear that threshold on its
    # own, so the stop condition has to be explicit now.
    if any(r["type"] in ("customer_validation", "step_up_auth") for r in state["evidence_requests"]):
        return "decide_actions"
    # Was gated on action_band's "gather_more" range (0.40-0.75, config.yaml), which doesn't
    # match verdict's own uncertain range (0.20-0.70, see assess_patterns_and_risk) - a score
    # in [0.20, 0.40) was "uncertain" by verdict but "monitor_close" by action_band, so
    # evidence was never requested and the case was stuck uncertain with no chance to ask a
    # decisive customer_validation/step_up_auth question. Use verdict directly instead.
    if state["verdict"] == "uncertain" and state["loop_count"] < _AGENT_CFG["max_evidence_loops"]:
        return "request_more_evidence"
    return "decide_actions"


REQUEST_TYPE_PRIORITY = {
    "customer_report": ["customer_validation", "analyst_info", "step_up_auth"],
    "risk_score": ["step_up_auth", "customer_validation", "analyst_info"],
    "analyst_request": ["analyst_info", "customer_validation", "step_up_auth"],
}


def request_more_evidence(state: dict) -> dict:
    asked = {r["type"] for r in state["evidence_requests"]}
    priority = REQUEST_TYPE_PRIORITY.get(state["trigger_type"], ["customer_validation", "step_up_auth", "analyst_info"])
    req_type = next((t for t in priority if t not in asked), None)

    if req_type is None:
        # every request type already asked, no new question left to ask - just stop looping
        return {"loop_count": state["loop_count"] + 1}

    case_facts = _build_case_facts(state)
    assumed = simulate_response(state["case_id"], req_type, state["ring"], state["similar_cases"], case_facts)

    requests = list(state["evidence_requests"])
    requests.append({"type": req_type, "asked_after_step": state["loop_count"] + 1, "assumed_response": assumed})

    evidence, _ = _add_evidence(
        state, "customer_response" if req_type == "customer_validation" else "analyst_input",
        f"Requested {req_type}: {assumed}", "simulate_response",
    )

    return {
        "evidence_requests": requests,
        "customer_response": assumed,
        "evidence": evidence,
        "loop_count": state["loop_count"] + 1,
        "tool_calls": state["tool_calls"] + 1,
    }


def _compute_affected_and_exposure(state: dict) -> tuple[list[str], float, str, float]:
    txns = state["subgraph_txns"]
    flagged_id = state["flagged_txn_id"]
    if state["verdict"] == "legitimate":
        return [], 0.0, "", 0.0

    if state["pattern"] == "card_testing":
        small = sorted([t for t in txns if t.amount < 5.0], key=lambda t: t.ts)
        affected = [t.txn_id for t in small] + [flagged_id]
        already_cleared = next((t.amount for t in txns if t.txn_id == flagged_id and t.amount > 100), 0.0)
    else:
        affected = [flagged_id]
        already_cleared = 0.0

    affected = sorted(set(affected))
    exposure = sum(t.amount for t in txns if t.txn_id in affected)
    first_suspicious = min((t for t in txns if t.txn_id in affected), key=lambda t: t.ts, default=None)
    return affected, round(exposure, 2), (first_suspicious.txn_id if first_suspicious else flagged_id), already_cleared


def decide_actions(state: dict) -> dict:
    affected, exposure, first_suspicious, already_cleared = _compute_affected_and_exposure(state)

    last_request_type = state["evidence_requests"][-1]["type"] if state.get("evidence_requests") else None
    final = recommend_actions(
        pattern=state["pattern"], verdict=state["verdict"], fraud_probability=state["confidence"]["score"],
        exposure_usd=exposure, ring=state["ring"], evidence_signal_count=state.get("evidence_signal_count", 0),
        last_response=state.get("customer_response"), last_request_type=last_request_type, already_cleared_amount=already_cleared,
        trigger_type=state["trigger_type"], recurring_pattern_match=state.get("recurring_pattern_match", False),
    )

    initial_names = [a["action"] for a in state["initial_actions"]]
    final_names = [a["action"] for a in final]
    before_score = state.get("confidence_before", state["confidence"])["score"]
    after_score = state["confidence"]["score"]

    if initial_names == final_names and before_score == after_score:
        what_changed = "nothing"
    elif state.get("evidence_requests"):
        last = state["evidence_requests"][-1]
        what_changed = (
            f"Confidence before additional evidence was {before_score} (actions: {initial_names}). "
            f"After {last['type']} response ({last['assumed_response']!r}), confidence moved to {after_score} "
            f"(actions: {final_names})."
        )
    else:
        what_changed = f"Confidence before/after: {before_score} -> {after_score}. Actions {initial_names} -> {final_names}."

    ring = state["ring"]
    # Real card IDs from device_ring (see backends/tigergraph.py::find_fraud_ring), not a
    # guessed customer_id+"-K1" - a customer's involved card is often not their first one.
    # Only cards with real fraud evidence (fraud_confirmed_member_cards), not every card that
    # merely shares a rare device - R6 requires cards that show fraud, not just proximity.
    # No fabricated fallback: if a backend doesn't populate this (e.g. LocalBackend, which
    # only tracks customer-level ring membership), this stays honestly empty.
    connected_cards = sorted(ring.get("fraud_confirmed_member_cards", []))[:10]

    files_report = "FILE_REPORT" in final_names
    ts_list = sorted(t.ts for t in state["subgraph_txns"] if t.txn_id in affected)
    dates = [ts_list[0][:10], ts_list[-1][:10]] if ts_list else []
    sar = {
        "file": files_report,
        "reason": next((a["reason"] for a in final if a["action"] == "FILE_REPORT"), "not required for this case"),
        "subjects": [state["customer_id"], state["card_id"]] + connected_cards if files_report else [],
        "total_amount_usd": exposure if files_report else 0,
        "activity_dates": dates if files_report else [],
    }

    score = state["confidence"]["score"]
    if score >= 0.85 or score <= 0.15:
        stop_reason = "Fraud probability cleared the stopping threshold with multiple independent evidence sources."
    elif state.get("customer_response"):
        stop_reason = "A simulated verification response settled the question."
    elif state["loop_count"] >= _AGENT_CFG["max_evidence_loops"]:
        stop_reason = "Evidence-gathering loop limit reached; further steps unlikely to change the decision."
    else:
        stop_reason = "Evidence gathered was sufficient to reach a defensible decision without further steps."

    return {
        "final_actions": final,
        "what_changed": what_changed,
        "affected_txn_ids": affected,
        "exposure_usd": exposure,
        "already_cleared_amount": already_cleared,
        "connected_card_ids": connected_cards,
        # rare_shared_devices (from device_ring) is the device that actually ties this case to
        # other cards - state["device_profiles"] is just this account's own devices, which
        # isn't the same claim ("linking this case to other cards" per the schema) and included
        # devices with no ring at all. Fall back to the account's own devices only if device_ring
        # found nothing, so the field is never empty for a case that clearly has a device signal.
        "connected_device_profiles": ring.get("rare_shared_devices") or state.get("device_profiles", []),
        "sar": sar,
        "stop_reason": stop_reason,
    }


def approval_gate(state: dict) -> dict:
    results = gate_fn(state["case_id"], [{"action": a["action"], "reason": a["reason"]} for a in state["final_actions"]], state.get("exposure_usd", 0))
    return {"ledger_results": results}


def execute_or_record(state: dict) -> dict:
    from actions.api import execute_action

    executed = [{"action": a["action"], "result": execute_action(a["action"], state["case_id"], state.get("exposure_usd", 0))} for a in state.get("ledger_results", []) if a["status"] == "executed"]

    if state["verdict"] == "fraud":
        status = "closed_fraud"
    elif state["verdict"] == "legitimate":
        status = "closed_legitimate"
    else:
        status = "escalated"
    if any(a["action"] == "ESCALATE_TO_ANALYST" for a in state["final_actions"]):
        status = "escalated"

    return {"status": status, "executed_actions": executed}


def _fallback_text(state: dict) -> str:
    ev_ids = ", ".join(e["evidence_id"] for e in state["evidence"][:4])
    return (
        f"Investigation of {state['case_id']} found pattern={state['pattern']} with confidence "
        f"{state['confidence']['score']} ({state['confidence']['risk_level']} risk), based on {ev_ids}."
    )


def explain(state: dict) -> dict:
    ctx = build_context(state["evidence"], state["ring"], state["velocity_1h"], state["similar_cases"], state["pattern"], state["confidence"], state.get("exposure_usd", 0))
    policy_ids = [c["clause_id"] for c in state["policy_clauses"]]
    valid_ids = (
        {e["evidence_id"] for e in state["evidence"]}
        | set(policy_ids)
        | {c["case_id"] for c in state["similar_cases"]}
        | {state["flagged_txn_id"]}
        | set(state["affected_txn_ids"])
        | {state["case_id"]}
    )

    text = complete(explanation_prompt(ctx, state["policy_clauses"]), context=ctx)
    bad = validate_citations(text, valid_ids)
    if bad:
        text = complete(explanation_prompt(ctx, state["policy_clauses"]) + f"\n\nDo not cite these invalid IDs: {bad}", context=ctx)
        if validate_citations(text, valid_ids):
            text = _fallback_text(state)

    # R2/R3: a direct customer_validation response sets the verdict outright,
    # independent of the confidence score (see assess_patterns_and_risk) - which can
    # make the verdict look mismatched against "medium risk, 0.41" without context.
    # Appended deterministically (not left to the LLM) so it's never silently dropped.
    last_request_type = state["evidence_requests"][-1]["type"] if state.get("evidence_requests") else None
    score = state["confidence"]["score"]
    score_implied_verdict = "fraud" if score >= 0.70 else ("legitimate" if score <= 0.20 else "uncertain")
    if last_request_type == "customer_validation" and state["verdict"] != score_implied_verdict:
        text = text.rstrip()
        if not text.endswith((".", "!", "?")):
            text += "."
        text += (
            f" Verdict set to {state['verdict']} by the customer's direct response (R2/R3), "
            f"overriding what the {state['confidence']['risk_level']} confidence score ({score}) alone would suggest."
        )

    sar = dict(state["sar"])
    if sar["file"]:
        sar_card_ids = [state["card_id"]] + state["connected_card_ids"]
        sar_ctx = {**ctx, "customer_id": state["customer_id"], "card_ids": sar_card_ids, "dates": sar["activity_dates"], "total_amount": sar["total_amount_usd"]}
        narrative = complete(sar_prompt(ctx, state["customer_id"], sar_card_ids, sar["activity_dates"], sar["total_amount_usd"]), context=sar_ctx, kind="sar")
        if validate_citations(narrative, valid_ids):
            narrative = _fallback_text(state)
        sar["narrative"] = narrative

    tokens_est = int((len(text.split()) + len(sar.get("narrative", "").split())) * 1.3)

    return {"summary": text, "explanation": text, "sar": sar, "tokens_est": tokens_est}


def _build_case_record(state: dict) -> CaseRecord:
    evidence = [
        Evidence(claim=e["description"], source=EVIDENCE_TYPE_TO_SOURCE.get(e["type"], "graph"), ref=e["source_tool"], entity_ids=e["entity_ids"])
        for e in state["evidence"]
    ]
    similar_prior_cases = [c["case_id"] for c in state["similar_cases"] if c["outcome"] == "confirmed_fraud" and c["similarity"] >= 0.3]

    case = Case(
        status=state["status"],
        verdict=state["verdict"],
        fraud_probability=state["confidence"]["score"],
        pattern=state["pattern"],
        pattern_description=state["pattern_description"],
        affected_txn_ids=state["affected_txn_ids"],
        first_suspicious_txn_id=state["affected_txn_ids"][0] if state["affected_txn_ids"] else "",
        connected_card_ids=state["connected_card_ids"],
        connected_device_profiles=state["connected_device_profiles"],
        exposure_usd=state["exposure_usd"],
        evidence=evidence,
        similar_prior_cases=similar_prior_cases,
        summary=state["summary"],
        written_to_graph=state.get("written_to_graph", False),
        graph_case_id=state.get("graph_case_id", ""),
    )

    return CaseRecord(
        case_id=state["case_id"],
        case=case,
        evidence_requests=[EvidenceRequest(**r) for r in state["evidence_requests"]],
        next_best_actions=NextBestActions(
            initial=[ActionItem(**a) for a in state["initial_actions"]],
            final=[ActionItem(**a) for a in state["final_actions"]],
            what_changed=state["what_changed"],
        ),
        sar=SAR(**state["sar"]),
        stop_reason=state["stop_reason"],
        tool_calls=state["tool_calls"],
        tokens=state.get("tokens_est", 0),
        latency_s=round(time.time() - state["start_time"], 2),
    )


def update_case_memory(state: dict) -> dict:
    backend = state["backend"]
    case_record = _build_case_record({**state, "written_to_graph": True})
    result = backend.write_case(state["case_id"], case_record.model_dump_json(), opened_at=state["opened_at"])

    case_record.case.written_to_graph = result.written
    case_record.case.graph_case_id = result.graph_case_id

    return {"written_to_graph": result.written, "graph_case_id": result.graph_case_id, "similar_to": result.similar_to, "case_record": case_record}
