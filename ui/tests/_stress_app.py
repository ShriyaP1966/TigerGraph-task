"""Standalone Streamlit script used only by test_dashboard_robustness.py.

Renders every dashboard component (not just one tab) against a single
synthetic case, selected via st.session_state["case_idx"]. Kept separate
from ui/app.py so stress-testing never touches the real app or its data
source.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # ui/
sys.path.insert(0, str(Path(__file__).resolve().parent))  # ui/tests/

import streamlit as st

from components import actions, approvals, confidence, detail, evidence
from fixtures import build_stress_cases
from lib.data import load_policy_clauses
from lib.graph_view import render_case_graph

cases = build_stress_cases()
idx = st.session_state.get("case_idx", 0)
case = cases[idx]
policy_clauses = load_policy_clauses()

st.write(f"Rendering: {case['case_id']}")

detail.render_case_header(case)
detail.render_trigger_and_entities(case)
evidence.render_evidence_timeline(case)
detail.render_findings(case)
detail.render_decision_log(case)
confidence.render_confidence_panel(case)
actions.render_recommended_actions(case, policy_clauses)
detail.render_sar(case)
detail.render_case_memory(case)
detail.render_explanation(case)
render_case_graph(case)
approvals.render_approval_queue(cases)
