"""Fraud Investigation analyst dashboard (P3).

Renders case data shaped like contracts/case_record_schema.json. Reads the
real cases/*.json answer files via api.py (see lib/data.py), falling back to
the mock contract only if no answer files exist yet.
"""

from __future__ import annotations

import streamlit as st

from components import actions, approvals, confidence, detail, evidence, queue
from lib import data, mock_actions
from lib.graph_view import render_case_graph
from lib.styling import inject_css

st.set_page_config(
    page_title="Fraud Investigation Dashboard",
    page_icon="\U0001F6E1",
    layout="wide",
)
st.markdown(inject_css(), unsafe_allow_html=True)

if "selected_case_id" not in st.session_state:
    st.session_state.selected_case_id = None
if "nav" not in st.session_state:
    st.session_state.nav = "Case Queue"
# Streamlit forbids writing to a widget-bound session_state key after that
# widget has been instantiated in the same run. Components that want to
# change tabs (e.g. queue -> detail on row click) set `nav_override` instead;
# it's applied here, before the st.radio(key="nav") below is created.
if "nav_override" in st.session_state:
    st.session_state.nav = st.session_state.pop("nav_override")

cases = mock_actions.apply_overlay(data.load_cases())
policy_clauses = data.load_policy_clauses()
pending_count = sum(
    1
    for case in cases
    for d in case.get("decisions_and_actions") or []
    if d.get("requires_approval") and d.get("status") in {"recommended", "pending_approval"}
)

with st.sidebar:
    st.title("Fraud Investigation")
    st.caption("HHGOA — TigerGraph Agentic Fraud Investigation")
    nav_labels = {"Approvals": f"Approvals ({pending_count} pending)" if pending_count else "Approvals"}
    st.radio(
        "Navigate",
        ["Case Queue", "Case Detail", "Approvals"],
        key="nav",
        format_func=lambda opt: nav_labels.get(opt, opt),
    )
    st.divider()
    if st.session_state.selected_case_id:
        st.caption(f"Open case: **{st.session_state.selected_case_id}**")
    st.caption(f"{len(cases)} case(s) loaded.")

st.title("Fraud Investigation Dashboard")

if st.session_state.nav == "Case Queue":
    selected = queue.render_case_queue(cases)
    if selected:
        st.session_state.selected_case_id = selected
        st.session_state.nav_override = "Case Detail"
        st.rerun()

elif st.session_state.nav == "Case Detail":
    case_id = st.session_state.selected_case_id
    case = data.get_case(cases, case_id) if case_id else None
    if not case:
        st.info("No case selected. Go to Case Queue and pick a case.")
    else:
        detail.render_case_header(case)
        detail.render_trigger_and_entities(case)

        tabs = st.tabs(["Evidence & Findings", "Confidence", "Actions & SAR", "Graph", "Case memory"])

        with tabs[0]:
            evidence.render_evidence_timeline(case)
            st.markdown("---")
            detail.render_findings(case)
            st.markdown("---")
            detail.render_decision_log(case)

        with tabs[1]:
            confidence.render_confidence_panel(case)

        with tabs[2]:
            actions.render_recommended_actions(case, policy_clauses)
            st.markdown("---")
            detail.render_sar(case)

        with tabs[3]:
            render_case_graph(case)

        with tabs[4]:
            detail.render_case_memory(case)
            st.markdown("---")
            detail.render_explanation(case)

elif st.session_state.nav == "Approvals":
    approvals.render_approval_queue(cases)
