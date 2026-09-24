"""Evidence timeline: everything in investigation_record.evidence_gathered,
in chronological order, with the same evidence_id used by Findings so an
analyst can trace a claim straight back to its source.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from lib.styling import esc

_TYPE_LABEL = {
    "graph_pattern": "Graph pattern",
    "transaction_history": "Transaction history",
    "device_signal": "Device signal",
    "identity_signal": "Identity signal",
    "prior_case": "Prior case",
    "policy": "Policy",
    "analyst_input": "Analyst input",
    "customer_response": "Customer response",
}


def _supporting_findings(case: dict[str, Any], evidence_id: str) -> list[str]:
    findings = (case.get("investigation_record") or {}).get("findings") or []
    return [f["finding_id"] for f in findings if evidence_id in (f.get("supporting_evidence") or [])]


def render_evidence_timeline(case: dict[str, Any]) -> None:
    evidence = (case.get("investigation_record") or {}).get("evidence_gathered") or []
    st.markdown('<div class="section-label">Evidence timeline</div>', unsafe_allow_html=True)

    if not evidence:
        st.caption("No evidence gathered yet.")
        return

    ordered = sorted(evidence, key=lambda e: e.get("timestamp", ""))
    for e in ordered:
        type_label = _TYPE_LABEL.get(e.get("type", ""), e.get("type", ""))
        findings = _supporting_findings(case, e.get("evidence_id", ""))
        findings_txt = f" · supports {', '.join(esc(fid) for fid in findings)}" if findings else ""
        st.markdown(
            f'<div class="evidence-row">'
            f'<b>{esc(e.get("evidence_id", ""))}</b> &nbsp; <span class="clause-chip">{esc(type_label)}</span>'
            f'<br>{esc(e.get("description", ""))}'
            f'<br><span class="muted">{esc(e.get("timestamp", ""))} · via {esc(e.get("source_tool", ""))}{findings_txt}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
