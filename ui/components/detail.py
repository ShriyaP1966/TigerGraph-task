"""Case detail: header/trigger/entities, findings, decision log, and SAR —
everything in the case record except the evidence timeline, confidence
panel, recommended actions and graph, which get their own components.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from lib.styling import case_status_badge, decision_status_badge, esc, risk_badge


def render_case_header(case: dict[str, Any]) -> None:
    risk = ((case.get("investigation_record") or {}).get("risk_assessment") or {})
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"## {esc(case['case_id'])}")
        badges = case_status_badge(case.get("status")) + "&nbsp;&nbsp;" + risk_badge(risk.get("risk_level"))
        st.markdown(badges, unsafe_allow_html=True)
    with col2:
        st.markdown(
            f'<div class="muted">Created</div><div>{esc(case.get("created_at", "—"))}</div>'
            f'<div class="muted" style="margin-top:6px;">Updated</div><div>{esc(case.get("updated_at", "—"))}</div>',
            unsafe_allow_html=True,
        )
    st.markdown("---")


def render_trigger_and_entities(case: dict[str, Any]) -> None:
    trigger = case.get("trigger", {}) or {}
    entities = case.get("entities", {}) or {}

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="section-label">Trigger</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="case-card">'
            f'<b>{esc(trigger.get("type", "—"))}</b> · <span class="secondary-text">{esc(trigger.get("source_id", ""))}</span><br>'
            f'<span class="muted">{esc(trigger.get("timestamp", ""))}</span><br><br>'
            f'{esc(trigger.get("details", ""))}'
            f"</div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown('<div class="section-label">Entities examined</div>', unsafe_allow_html=True)
        lines = []
        if entities.get("customer_id"):
            lines.append(f"Customer: {esc(entities['customer_id'])}")
        if entities.get("account_ids"):
            lines.append(f"Accounts: {', '.join(esc(a) for a in entities['account_ids'])}")
        if entities.get("transaction_ids"):
            lines.append(f"Transactions: {', '.join(esc(t) for t in entities['transaction_ids'])}")
        if entities.get("device_ids"):
            lines.append(f"Devices: {', '.join(esc(d) for d in entities['device_ids'])}")
        body = "<br>".join(lines) if lines else "No entities recorded."
        st.markdown(f'<div class="case-card">{body}</div>', unsafe_allow_html=True)


def render_findings(case: dict[str, Any]) -> None:
    investigation = case.get("investigation_record", {}) or {}
    findings = investigation.get("findings") or []
    pattern = investigation.get("fraud_pattern_identified")

    st.markdown('<div class="section-label">Findings</div>', unsafe_allow_html=True)
    if pattern:
        st.markdown(f'<span class="clause-chip">Pattern: {esc(pattern)}</span>', unsafe_allow_html=True)
    if not findings:
        st.caption("No findings recorded yet.")
        return
    for f in findings:
        evidence_refs = ", ".join(esc(e) for e in (f.get("supporting_evidence") or [])) or "none"
        st.markdown(
            f'<div class="finding-row"><b>{esc(f.get("finding_id", ""))}</b> — {esc(f.get("description", ""))}'
            f'<br><span class="muted">Supported by: {evidence_refs}</span></div>',
            unsafe_allow_html=True,
        )


def render_decision_log(case: dict[str, Any]) -> None:
    decisions = case.get("decisions_and_actions") or []
    st.markdown('<div class="section-label">Decision log</div>', unsafe_allow_html=True)
    if not decisions:
        st.caption("No decisions recorded yet.")
        return
    for d in decisions:
        action_label = (d.get("action", "") or "").replace("_", " ").capitalize()
        st.markdown(
            f'<div class="case-card">'
            f'<b>{esc(action_label)}</b> &nbsp; {decision_status_badge(d.get("status"))}'
            f'<br><span class="secondary-text">{esc(d.get("decision", ""))}</span>'
            f'<br><span class="muted">{esc(d.get("actor", ""))} · {esc(d.get("timestamp", ""))}'
            f' · approval: {esc(d.get("approval_route", ""))} · requires approval: '
            f'{"yes" if d.get("requires_approval") else "no"}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )


def render_sar(case: dict[str, Any]) -> None:
    sar = case.get("sar", {}) or {}
    st.markdown('<div class="section-label">Suspicious activity report (SAR)</div>', unsafe_allow_html=True)
    if not sar.get("filed"):
        st.caption("Not filed for this case.")
        return
    clauses = ", ".join(esc(c) for c in (sar.get("policy_clause_ids") or [])) or "none cited"
    st.markdown(
        f'<div class="case-card">{esc(sar.get("content", ""))}'
        f'<br><br><span class="muted">Policy clauses cited: {clauses}</span></div>',
        unsafe_allow_html=True,
    )


def render_case_memory(case: dict[str, Any]) -> None:
    memory = case.get("case_memory", {}) or {}
    st.markdown('<div class="section-label">Case memory</div>', unsafe_allow_html=True)
    stored = "Yes" if memory.get("stored") else "No"
    st.caption(f"Written to graph: {stored}")
    prior = memory.get("similar_prior_cases_used") or []
    if not prior:
        st.caption("No similar prior cases retrieved.")
        return
    for p in prior:
        sim = p.get("similarity_score")
        sim_txt = f"{sim:.2f}" if isinstance(sim, (int, float)) else "—"
        st.markdown(
            f'<span class="clause-chip">{esc(p.get("case_id", ""))} · similarity {sim_txt} · {esc(p.get("outcome", ""))}</span>',
            unsafe_allow_html=True,
        )


def render_explanation(case: dict[str, Any]) -> None:
    explanation = case.get("explanation")
    if not explanation:
        return
    st.markdown('<div class="section-label">Explanation</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="case-card">{esc(explanation)}</div>', unsafe_allow_html=True)
