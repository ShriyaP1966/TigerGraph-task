"""Builds the structured, summarized context handed to the LLM (never raw
transaction rows) and the prompts for the two things the LLM is used for:
typology reasoning and the final explanation narrative.
"""
import re


def build_context(evidence: list[dict], ring: dict, velocity: dict, similar_cases: list[dict], pattern: str, confidence: dict, exposure_usd: float = 0) -> dict:
    # ring["size"] is uncapped (see graph/queries/device_ring.gsql) - a common device/region can
    # inflate it into the thousands, which is meaningless in prose ("linked to a 7981-member
    # cluster"). member_card_ids is the cardinality-capped, real signal; when it's empty,
    # only trust the raw size if it's small enough to plausibly be a real ring rather than
    # noise from a common shared attribute.
    _members = ring.get("member_card_ids", [])
    _raw_size = ring.get("size", 1)
    ring_size = (len(_members) + 1) if _members else (_raw_size if _raw_size <= 100 else 1)
    # known_fraud_count is raw/uncapped too (can be in the thousands, same reason as
    # ring_size above) - fraud_confirmed_member_cards is the real, evidence-filtered count
    # (see backends/tigergraph.py::_filter_fraud_confirmed), always <= ring_size by
    # construction so "N related, M confirmed fraud" stays internally consistent in prose.
    ring_known_fraud = len(ring.get("fraud_confirmed_member_cards", []))
    return {
        "evidence": [{"id": e["evidence_id"], "claim": e["description"]} for e in evidence],
        "ring_size": ring_size,
        "ring_known_fraud": ring_known_fraud,
        "velocity_count": velocity.get("count", 0),
        "velocity_z_score": round(velocity.get("z_score", 0), 2),
        "similar_cases": [{"case_id": c["case_id"], "similarity": c["similarity"], "outcome": c["outcome"]} for c in similar_cases],
        "pattern": pattern,
        "confidence_score": confidence.get("score"),
        "risk_level": confidence.get("risk_level"),
        "exposure_usd": exposure_usd,
    }


def explanation_prompt(context: dict, policy_clauses: list[dict]) -> str:
    ev_lines = "\n".join(f"- {e['id']}: {e['claim']}" for e in context["evidence"])
    policy_lines = "\n".join(f"- {c['clause_id']}: {c['text'][:200]}" for c in policy_clauses)
    return f"""You are a fraud investigation analyst writing a short case explanation.

Evidence gathered:
{ev_lines}

Ring size: {context['ring_size']} (known fraud in ring: {context['ring_known_fraud']})
Velocity: {context['velocity_count']} transactions, z-score {context['velocity_z_score']}
Similar prior cases: {context['similar_cases']}
Identified pattern: {context['pattern']}
Confidence: {context['confidence_score']} ({context['risk_level']} risk)
Exposure (the actual dollar total for THIS case - use this exact figure, never a
number from a policy clause's threshold text): ${context['exposure_usd']}

Full policy, for reference only - most of these do not apply to this specific case:
{policy_lines}

Write 2-4 sentences explaining the finding. Cite evidence by ID (e.g. EV-001) inline.
Cite AT MOST 1-2 policy clauses by ID (e.g. POL-004) - only the ones whose actual text
is genuinely relevant to this case's reasoning, never the whole list. Only cite IDs
listed above. Do not invent transaction, card, or case IDs not present in the evidence.
Any dollar amount you state must be the exposure figure given above, not a number
copied from a policy clause's threshold."""


def sar_prompt(context: dict, customer_id: str, card_ids: list[str], dates: list[str], total_amount: float) -> str:
    ev_lines = "\n".join(f"- {e['id']}: {e['claim']}" for e in context["evidence"])
    return f"""Write a suspicious activity report narrative (6-12 sentences) for a bank
regulatory filing. It must stand on its own: who, what, when, where, how, why suspicious.

Customer: {customer_id}
Cards: {card_ids}
Activity dates: {dates}
Total amount: ${total_amount}
Pattern: {context['pattern']}
Evidence:
{ev_lines}

Do not invent IDs, dates, or amounts not given above."""


ID_PATTERN = re.compile(r"\b(EV-\d+|POL-\d+|TYP-\d+|CC-\d+|T\d+|HHG-\d+)\b")


def extract_cited_ids(text: str) -> set[str]:
    return set(ID_PATTERN.findall(text))


def validate_citations(text: str, valid_ids: set[str]) -> list[str]:
    """returns the list of cited IDs that aren't in valid_ids - empty list means clean"""
    cited = extract_cited_ids(text)
    return sorted(cited - valid_ids)
