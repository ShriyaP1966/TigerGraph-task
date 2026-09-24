"""Deterministic confidence score. No LLM in here - the agent computes each
0-1 component from evidence (rule-based), this just does the weighted sum and
explains itself. Keeping this pure makes it trivial to unit test and tune.
"""
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
_CFG = yaml.safe_load((REPO_ROOT / "config.yaml").read_text())


def compute_confidence(bank_risk: float, typology_match: float, similarity_to_fraud: float, evidence_coverage: float) -> dict:
    w = _CFG["confidence_weights"]
    components = {
        "bank_risk_score": (bank_risk, w["bank_risk"], "the flagged transaction's own risk_score from the bank's model"),
        "typology_match_strength": (typology_match, w["typology_match"], "how well the evidence matches a known fraud pattern's indicators"),
        "similarity_to_confirmed_fraud": (similarity_to_fraud, w["similarity_to_fraud"], "similarity to the closest confirmed-fraud prior case"),
        "evidence_coverage": (evidence_coverage, w["evidence_coverage"], "fraction of the standard evidence checklist actually gathered"),
    }

    breakdown = {}
    total = 0.0
    for name, (value, weight, reason) in components.items():
        contribution = value * weight
        total += contribution
        breakdown[name] = {"value": round(value, 4), "weight": weight, "contribution": round(contribution, 4), "reason": reason}

    return {"score": round(total, 4), "breakdown": breakdown, "risk_level": risk_level(total)}


def risk_level(score: float) -> str:
    t = _CFG["confidence_thresholds"]
    if score >= t["act"]:
        return "high"
    if score >= t["gather_more"]:
        return "medium"
    return "low"


# (request_type, indicates_fraud) -> signed adjustment. A direct customer answer (R2/R3)
# is the most conclusive evidence the policy defines, so it moves the score furthest.
# Step-up/analyst responses are real but softer signals, so they move it less.
#
# Previously this floored/capped the score to a fixed constant (e.g. always exactly 0.85
# for any fraud-indicating customer_validation, regardless of whether the underlying
# evidence was borderline or strong) - which collapsed every case that hit a given
# request_type/direction onto the same handful of scores (confirmed by tracing all 20
# cases: raw formula scores ranged smoothly 0.297-0.69 with no clustering at all; the
# post-override scores clustered hard at 0.3/0.75/0.85 purely from the snap-to-constant,
# discarding the real distinction between a weak and a strong case that both got the same
# customer response). An additive nudge keeps that distinction while still moving the
# score decisively in the response's direction.
RESPONSE_OVERRIDE_ADJUSTMENTS = {
    ("customer_validation", True): 0.15,
    ("customer_validation", False): -0.15,
    ("step_up_auth", True): 0.10,
    ("step_up_auth", False): -0.10,
    ("analyst_info", True): 0.10,
    ("analyst_info", False): -0.10,
}


def apply_response_override(confidence: dict, request_type: str, indicates_fraud: bool) -> dict:
    """Applies a documented adjustment to the FINAL score after a verification response,
    without touching the per-component breakdown (which stays an honest read of the
    evidence gathered). A customer denial doesn't change the flagged transaction's own
    risk_score or how well it matches a typology - it answers the fraud question directly,
    so it moves the score, not the inputs that produced it."""
    adjustment = RESPONSE_OVERRIDE_ADJUSTMENTS.get((request_type, indicates_fraud))
    if adjustment is None:
        return confidence
    new_score = round(min(max(confidence["score"] + adjustment, 0.0), 1.0), 4)
    if new_score == confidence["score"]:
        return confidence
    out = dict(confidence)
    out["score"] = new_score
    out["risk_level"] = risk_level(new_score)
    out["override"] = f"{request_type} response ({'fraud-indicating' if indicates_fraud else 'clears the account'}) moved score {confidence['score']} -> {out['score']}"
    return out


def action_band(score: float) -> str:
    """act | gather_more | monitor_close"""
    t = _CFG["confidence_thresholds"]
    if score >= t["act"]:
        return "act"
    if score >= t["gather_more"]:
        return "gather_more"
    return "monitor_close"
