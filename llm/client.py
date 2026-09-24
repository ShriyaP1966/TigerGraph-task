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


def complete(prompt: str, context: dict | None = None) -> str:
    mode = os.environ.get("LLM_MODE", "fixture")
    if mode == "fixture":
        return _fixture_response(context)

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
