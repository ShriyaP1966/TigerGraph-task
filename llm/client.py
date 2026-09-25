"""Groq primary, Gemini fallback, FIXTURE mode for dev without burning API quota.
Used only for typology reasoning prose and the explanation/SAR narrative - the
pattern enum, confidence score, and policy actions are all decided elsewhere,
deterministically.
"""
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# llama-3.3-70b-versatile was retired from Groq's catalog; gpt-oss-120b is the
# current best free-tier general chat model there (checked via client.models.list())
GROQ_MODEL = "openai/gpt-oss-120b"
GEMINI_MODEL = "gemini-1.5-flash"


def _fixture_response(context: dict | None) -> str:
    if not context:
        return "Investigation complete based on available evidence."

    ev_ids = [e["id"] for e in context.get("evidence", [])]
    cite = ", ".join(ev_ids) if ev_ids else "no direct evidence"
    pattern = context.get("pattern", "none")
    ring = context.get("ring_size", 1)

    parts = [f"Evidence {cite} was reviewed."]
    if pattern and pattern != "none":
        parts.append(f"The activity is consistent with {pattern.replace('_', ' ')} (POL-004).")
    if ring and ring > 1:
        parts.append(f"The account is linked to a {ring}-member cluster with {context.get('ring_known_fraud', 0)} known-fraud members.")
    if context.get("similar_cases"):
        top = context["similar_cases"][0]
        parts.append(f"Most similar prior case: {top['case_id']} (similarity {top['similarity']}, outcome {top['outcome']}).")
    parts.append(f"Confidence {context.get('confidence_score')} ({context.get('risk_level')} risk).")
    return " ".join(parts)


# gpt-oss-120b writes citations like "EV<U+2011>001" using a typographic non-breaking
# hyphen instead of ASCII "-" - llm/prompts.py's ID_PATTERN (EV-\d+) doesn't match that,
# so validate_citations() silently never flags a hallucinated ID that happens to use one
# of these characters. Normalizing to ASCII fixes both the validation blind spot and
# keeps stored case files readable with plain "EV-001" rather than a lookalike glyph.
_DASH_CHARS = "‐‑‒–—−"
_SPACE_CHARS = "    "
_TYPOGRAPHY_TABLE = str.maketrans({c: "-" for c in _DASH_CHARS} | {c: " " for c in _SPACE_CHARS})


def _normalize_typography(text: str) -> str:
    return text.translate(_TYPOGRAPHY_TABLE)


def _fixture_sar_narrative(context: dict | None) -> str:
    """SAR narratives need who/what/when/where/how/why in 6-12 sentences
    (DATASET_README.md sar.narrative field + section 3a) - _fixture_response's
    generic 4-5 sentence blurb doesn't carry customer/card/date/amount at
    all, so under LLM_MODE=fixture every SAR narrative was identical
    boilerplate regardless of the actual case. Built deterministically from
    real case data, same as everywhere else non-LLM in this agent."""
    if not context:
        return "Suspicious activity report: insufficient context to generate a narrative."

    customer_id = context.get("customer_id", "the customer")
    card_ids = context.get("card_ids") or []
    cards_str = " and ".join(card_ids) if card_ids else "the flagged card"
    dates = context.get("dates") or []
    if len(dates) == 2 and dates[0] == dates[1]:
        when = f"on {dates[0]}"
    elif len(dates) == 2:
        when = f"between {dates[0]} and {dates[1]}"
    else:
        when = "on the date(s) identified in the investigation"
    amount = context.get("total_amount", 0) or 0
    pattern = context.get("pattern", "none")
    pattern_str = pattern.replace("_", " ") if pattern and pattern != "none" else "activity inconsistent with this cardholder's established pattern"
    ev_claims = [e["claim"] for e in context.get("evidence", [])]
    ring_size = context.get("ring_size", 1) or 1
    ring_known_fraud = context.get("ring_known_fraud", 0) or 0

    sentences = [
        f"This report concerns customer {customer_id}, associated with card(s) {cards_str}.",
        f"The bank identified activity consistent with {pattern_str}, {when}, totaling ${amount:.2f} in exposure.",
    ]
    for claim in ev_claims[:4]:
        claim = claim.strip().rstrip(".")
        sentences.append(f"{claim[:1].upper()}{claim[1:]}.")
    if ring_size > 1:
        sentences.append(
            f"This activity connects to a broader cluster of {ring_size} related card(s)"
            + (f", {ring_known_fraud} of which have confirmed prior fraud." if ring_known_fraud else ", sharing the same origin identified above.")
        )
    sentences.append(
        f"Given the pattern, timing, and connected activity described above, this is assessed as suspicious "
        f"and meets the bank's threshold for regulatory reporting."
    )
    sentences.append(f"The affected card(s) have been placed under protective action pending further review.")

    # Floor of 6, cap of 12, per the Answer Format's exact bound
    while len(sentences) < 6:
        sentences.append("No further activity outside the scope described above was identified in the investigation window.")
    return " ".join(sentences[:12])


def _call_groq(prompt: str) -> str:
    from groq import Groq

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=900,  # gpt-oss spends part of the budget on hidden reasoning tokens before the visible answer
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()


def _call_gemini(prompt: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(GEMINI_MODEL)
    resp = model.generate_content(prompt)
    return resp.text.strip()


def complete(prompt: str, context: dict | None = None, kind: str = "explanation") -> str:
    mode = os.environ.get("LLM_MODE", "fixture")
    if mode == "fixture":
        return _fixture_sar_narrative(context) if kind == "sar" else _fixture_response(context)

    if os.environ.get("GROQ_API_KEY"):
        try:
            return _normalize_typography(_call_groq(prompt))
        except Exception as e:
            logger.warning("groq call failed (%s), trying gemini", e)

    if os.environ.get("GEMINI_API_KEY"):
        try:
            return _normalize_typography(_call_gemini(prompt))
        except Exception as e:
            logger.warning("gemini call failed (%s), falling back to fixture", e)

    logger.warning("no working LLM provider, falling back to fixture response")
    return _fixture_response(context)
