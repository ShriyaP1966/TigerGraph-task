"""Deterministic, rule-of-thumb typology matching - no LLM. Each match_* returns
a 0-1 strength based on how many of the typology's stated indicators are present.
These are heuristics for a 2-day build, not a trained model; tune the thresholds
after looking at real results on the 20 cases.
"""
from datetime import datetime


def _ts(t) -> datetime:
    return datetime.fromisoformat(t.ts.replace("Z", "+00:00")) if "Z" in t.ts or "+" in t.ts else datetime.fromisoformat(t.ts)


def match_card_testing(txns: list, flagged_id: str) -> float:
    small = sorted([t for t in txns if t.amount < 5.0], key=lambda t: t.ts)
    if len(small) < 3:
        return 0.0
    times = [_ts(t) for t in small]
    clustered = any((times[i + 2] - times[i]).total_seconds() <= 3600 for i in range(len(times) - 2))
    if not clustered:
        return 0.2
    flagged = next((t for t in txns if t.txn_id == flagged_id), None)
    followed_by_larger = flagged is not None and flagged.amount > 50 and flagged.txn_id not in {t.txn_id for t in small}
    return 0.95 if followed_by_larger else 0.6


def match_new_device(txns: list, flagged_id: str) -> float:
    flagged = next((t for t in txns if t.txn_id == flagged_id), None)
    if flagged is None or flagged.channel != "online":
        return 0.0
    return 0.7 if flagged.device_new else 0.0


def match_card_not_present(txns: list, flagged_id: str) -> float:
    flagged = next((t for t in txns if t.txn_id == flagged_id), None)
    if flagged is None or flagged.channel != "online":
        return 0.0
    window_txns = [t for t in txns if t.channel == "online" and abs((_ts(t) - _ts(flagged)).total_seconds()) <= 48 * 3600]
    burst = 0.5 if 2 <= len(window_txns) <= 4 else 0.2
    return min(burst + (0.2 if flagged.device_new else 0), 0.9)


def match_out_of_region(txns: list, flagged_id: str) -> float:
    flagged = next((t for t in txns if t.txn_id == flagged_id), None)
    if flagged is None or flagged.channel != "in_person" or flagged.addr1 is None:
        return 0.0
    history = [t.addr1 for t in txns if t.addr1 and t.txn_id != flagged_id]
    if not history:
        return 0.3  # no history to compare against, weak signal either way
    home_region = max(set(history), key=history.count)
    return 0.85 if flagged.addr1 != home_region else 0.0


def match_account_takeover(txns: list, flagged_id: str) -> float:
    # No ring signal here (deliberately - see choose_pattern): account_takeover is a
    # single-account signal (mixed channel + a device this account hasn't used before). A
    # shared-device-with-other-fraud signal is a *different* claim (coordinated abuse across
    # customers) and gets its own path to "undocumented" below, so the two don't collapse
    # into one score and mislabel a ring-driven case as account_takeover.
    channels = {t.channel for t in txns}
    mixed_channel = len(channels) > 1
    flagged = next((t for t in txns if t.txn_id == flagged_id), None)
    anomaly = flagged is not None and flagged.device_new
    score = 0.3 * mixed_channel + 0.3 * bool(anomaly)
    return score if score >= 0.3 else 0.0


def choose_pattern(txns: list, flagged_id: str, ring: dict, trigger_type: str | None = None) -> tuple[str, float]:
    scores = {
        "card_testing": match_card_testing(txns, flagged_id),
        "card_not_present_new_device": match_new_device(txns, flagged_id),
        "card_not_present_fraud": match_card_not_present(txns, flagged_id),
        "out_of_region_use": match_out_of_region(txns, flagged_id),
        "account_takeover": match_account_takeover(txns, flagged_id),
    }
    best_pattern, best_score = max(scores.items(), key=lambda kv: kv[1])

    # R9: coordinated abuse fitting no known pattern. fraud_confirmed_member_cards is the
    # cardinality-capped, real-evidence-filtered ring signal (see
    # backends/tigergraph.py::_filter_fraud_confirmed) - several OTHER cards sharing a rare
    # device (now <=~15 cards, not just <=60) that independently show real fraud (a
    # confirmed closed case only - not an elevated risk_score, which DATASET_README.md notes
    # is common rather than rare in this dataset).
    #
    # Restricted to analyst_request-triggered cases (e.g. HHG-014's "several cards this
    # month show purchases from the same unusual device profile" ask): a shared device is
    # measuring a dataset-wide correlation (device-ring fraud-confirmed fractions run
    # 34-80% across nearly the whole 20-case pack - not case-specific signal), so it's only
    # trustworthy enough to DRIVE the pattern/verdict when the trigger itself is explicitly
    # asking "is this device shared with other fraud". For customer_report/risk_score
    # triggers it stays visible as supporting evidence (gather_graph_evidence still cites
    # it) but doesn't compete for the pattern here.
    if trigger_type == "analyst_request":
        fraud_confirmed = len(ring.get("fraud_confirmed_member_cards", []))
        if fraud_confirmed > 0:
            undocumented_score = min(0.5 + 0.05 * fraud_confirmed, 0.95)
            if undocumented_score > best_score:
                return "undocumented", undocumented_score

    if best_score < 0.3:
        return "none", 0.0
    return best_pattern, best_score
