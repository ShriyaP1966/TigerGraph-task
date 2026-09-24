"""Confidence / uncertainty view: the confidence_score and its
confidence_breakdown components, exactly as the schema defines them — no new
scoring formula, just a clear rendering of what P2's agent already computed.

"Sufficient evidence" is read off the case's own `status` field (schema
enum: open/gathering_evidence/pending_customer_response mean more evidence
is still being sought; pending_approval/closed_* mean the agent judged it
had enough to act), not a new threshold invented in the UI.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from lib.styling import INK_MUTED, esc, risk_badge, sequential_step

_INSUFFICIENT_STATUSES = {"open", "gathering_evidence", "pending_customer_response"}

_COMPONENT_LABEL = {
    "bank_risk_score": "Bank risk score",
    "typology_match_strength": "Typology match strength",
    "similarity_to_confirmed_fraud": "Similarity to confirmed fraud",
    "evidence_coverage_ratio": "Evidence coverage ratio",
}


def render_confidence_panel(case: dict[str, Any]) -> None:
    risk = (case.get("investigation_record") or {}).get("risk_assessment") or {}
    st.markdown('<div class="section-label">Confidence &amp; uncertainty</div>', unsafe_allow_html=True)

    score = risk.get("confidence_score")
    col1, col2 = st.columns([1, 2])
    with col1:
        score_txt = f"{score:.2f}" if isinstance(score, (int, float)) else "—"
        st.markdown(f'<div class="metric-value">{score_txt}</div>', unsafe_allow_html=True)
        st.markdown('<div class="muted">Overall confidence score</div>', unsafe_allow_html=True)
        st.markdown(f"<div style='margin-top:8px;'>{risk_badge(risk.get('risk_level'))}</div>", unsafe_allow_html=True)

    with col2:
        status = case.get("status")
        if status in _INSUFFICIENT_STATUSES:
            st.markdown(
                f'<div class="case-card" style="border-left:3px solid #fab219;">'
                f'<b>Evidence gathering in progress</b> — case status is '
                f'<code>{esc(status)}</code>. The agent has not yet judged the evidence sufficient to act.'
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="case-card" style="border-left:3px solid #0ca30c;">'
                f'<b>Evidence judged sufficient to act</b> — case status is '
                f"<code>{esc(status)}</code>.</div>",
                unsafe_allow_html=True,
            )
        rationale = risk.get("rationale")
        if rationale:
            st.markdown(f'<div class="secondary-text" style="margin-top:8px;">{esc(rationale)}</div>', unsafe_allow_html=True)

    breakdown = risk.get("confidence_breakdown") or {}
    if not breakdown:
        return

    st.markdown('<div class="section-label" style="margin-top:16px;">Confidence components</div>', unsafe_allow_html=True)
    for key, value in breakdown.items():
        label = _COMPONENT_LABEL.get(key, key.replace("_", " ").capitalize())
        value = value if isinstance(value, (int, float)) else 0.0
        pct = max(0.0, min(1.0, value)) * 100
        color = sequential_step(value)
        st.markdown(
            f'<div style="margin-bottom:10px;">'
            f'<div style="display:flex;justify-content:space-between;font-size:0.85rem;">'
            f'<span>{esc(label)}</span><span style="color:{INK_MUTED};">{value:.2f}</span></div>'
            f'<div style="background:#e1e0d9;border-radius:4px;height:8px;width:100%;">'
            f'<div style="background:{color};border-radius:4px;height:8px;width:{pct:.0f}%;"></div>'
            f"</div></div>",
            unsafe_allow_html=True,
        )
