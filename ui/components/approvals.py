"""Human-in-the-loop approval queue: every decisions_and_actions[] entry,
across all cases, where requires_approval is true and status is still
recommended/pending_approval. Approve/Reject write through
lib.mock_actions.record_decision(), which now calls the real api.approve()
(sqlite-backed policy ledger) — the only place that mutates decision status.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from lib import mock_actions
from lib.styling import approval_route_badge, decision_status_badge, esc

_PENDING_STATUSES = {"recommended", "pending_approval"}
_ANALYST_ACTOR = "analyst (dashboard)"


def render_approval_queue(cases: list[dict[str, Any]]) -> None:
    st.markdown('<div class="section-label">Pending approvals</div>', unsafe_allow_html=True)
    st.caption(
        "Actions that require human sign-off before being executed. Approve/Reject write to the real "
        "action ledger (ledger.sqlite3) via api.approve() — the same policy gate the agent itself uses."
    )

    pending: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for case in cases:
        for d in case.get("decisions_and_actions") or []:
            if d.get("requires_approval") and d.get("status") in _PENDING_STATUSES:
                pending.append((case, d))

    if not pending:
        st.success("No actions currently awaiting approval.")
        return

    for case, decision in pending:
        action_label = (decision.get("action", "") or "").replace("_", " ").capitalize()
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(
                f'<div class="case-card">'
                f'<b>{esc(case["case_id"])}</b> &nbsp; {decision_status_badge(decision.get("status"))} '
                f'&nbsp; {approval_route_badge(decision.get("approval_route"))}'
                f'<br><b>{esc(action_label)}</b>'
                f'<br><span class="secondary-text">{esc(decision.get("decision", ""))}</span>'
                f'<br><span class="muted">{esc(decision.get("actor", ""))} · {esc(decision.get("timestamp", ""))}</span>'
                f"</div>",
                unsafe_allow_html=True,
            )
        with col2:
            key_base = f"{case['case_id']}::{decision['decision_id']}"
            if st.button("Approve", key=f"approve::{key_base}", width="stretch", type="primary"):
                mock_actions.record_decision(case["case_id"], decision["decision_id"], "approved", _ANALYST_ACTOR)
                st.rerun()
            if st.button("Reject", key=f"reject::{key_base}", width="stretch"):
                mock_actions.record_decision(case["case_id"], decision["decision_id"], "rejected", _ANALYST_ACTOR)
                st.rerun()
