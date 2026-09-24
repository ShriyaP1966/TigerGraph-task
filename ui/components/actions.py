"""Recommended actions: next_best_action (before/after any requested
evidence) plus the SAR's cited policy clauses, resolved against the real
chunked policy (docs/policy/chunks/policy_clauses.json) so an analyst can
expand a clause ID to read the actual rule text.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from lib.styling import approval_route_badge, esc


def _render_nba_block(title: str, block: dict[str, Any] | None) -> None:
    block = block or {}
    action = (block.get("action") or "").replace("_", " ").capitalize() or "—"
    st.markdown(
        f'<div class="case-card">'
        f'<div class="muted">{esc(title)}</div>'
        f'<b>{esc(action)}</b> &nbsp; {approval_route_badge(block.get("approval_route"))}'
        f'<br><span class="secondary-text">{esc(block.get("rationale", ""))}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )


def render_recommended_actions(case: dict[str, Any], policy_clauses: dict[str, dict[str, Any]]) -> None:
    nba = case.get("next_best_action") or {}
    before = nba.get("before_additional_evidence")
    after = nba.get("after_additional_evidence")

    st.markdown('<div class="section-label">Next best action</div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        _render_nba_block("Before additional evidence", before)
    with col2:
        _render_nba_block("After additional evidence", after)

    if before and after:
        changed = before.get("action") != after.get("action") or before.get("approval_route") != after.get(
            "approval_route"
        )
        note = "Recommendation changed after evidence was gathered." if changed else "Recommendation unchanged."
        st.caption(note)

    requests = case.get("additional_evidence_requests") or []
    if requests:
        st.markdown('<div class="section-label" style="margin-top:12px;">Additional evidence requested</div>', unsafe_allow_html=True)
        for r in requests:
            req_type = (r.get("type") or "").replace("_", " ").capitalize()
            requested_at = (r.get("requested_at") or "").replace("_", " ")
            result_txt = f' · result: {esc(r["result"])}' if r.get("result") else ""
            st.markdown(
                f'<div class="case-card">'
                f'<b>{esc(req_type)}</b> · {esc(requested_at)}'
                f'<br><span class="secondary-text">{esc(r.get("reason", ""))}</span>'
                f'<br><span class="muted">status: {esc(r.get("status", ""))}{result_txt}</span>'
                f"</div>",
                unsafe_allow_html=True,
            )

    sar = case.get("sar") or {}
    clause_ids = sar.get("policy_clause_ids") or []
    if clause_ids:
        st.markdown('<div class="section-label" style="margin-top:12px;">Policy clauses cited (SAR)</div>', unsafe_allow_html=True)
        for cid in clause_ids:
            clause = policy_clauses.get(cid)
            if clause:
                with st.expander(f"{cid} — {clause['title']}"):
                    st.write(clause["text"])
            else:
                st.markdown(f'<span class="clause-chip">{esc(cid)} (not found in loaded policy chunks)</span>', unsafe_allow_html=True)
