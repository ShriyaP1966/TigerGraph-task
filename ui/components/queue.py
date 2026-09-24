"""Case queue: the analyst's landing view — one sortable row per case, dense
enough to triage at a glance. Selecting a row is the entry point into the
detail view.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st


def _current_action_label(case: dict[str, Any]) -> str:
    decisions = case.get("decisions_and_actions") or []
    if decisions:
        action = decisions[-1].get("action", "")
    else:
        nba = case.get("next_best_action") or {}
        action = (nba.get("after_additional_evidence") or {}).get("action", "")
    return action.replace("_", " ").capitalize() if action else "—"


def render_case_queue(cases: list[dict[str, Any]]) -> str | None:
    """Render the queue table and return the case_id of the selected row,
    or None if nothing is selected."""
    if not cases:
        st.warning("No cases available. Check contracts/case_record_example.json.")
        return None

    rows = []
    for c in cases:
        trigger = c.get("trigger", {}) or {}
        risk = ((c.get("investigation_record") or {}).get("risk_assessment") or {})
        rows.append(
            {
                "Case ID": c["case_id"],
                "Trigger": f"{trigger.get('type', '')} · {trigger.get('source_id', '')}",
                "Status": (c.get("status", "") or "").replace("_", " "),
                "Risk": risk.get("risk_level", "—"),
                "Confidence": risk.get("confidence_score"),
                "Recommended action": _current_action_label(c),
                "Updated": c.get("updated_at", ""),
            }
        )
    df = pd.DataFrame(rows)

    st.markdown('<div class="section-label">Case queue</div>', unsafe_allow_html=True)
    st.caption(f"{len(cases)} case(s) · click a row to open its case detail")

    event = st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config={
            "Confidence": st.column_config.ProgressColumn(
                "Confidence", min_value=0.0, max_value=1.0, format="%.2f"
            ),
        },
        on_select="rerun",
        selection_mode="single-row",
        key="case_queue_table",
    )

    selected_rows: list[int] = []
    try:
        selected_rows = list(event.selection["rows"])  # type: ignore[attr-defined]
    except (AttributeError, TypeError, KeyError):
        selected_rows = []

    if selected_rows:
        return str(df.iloc[selected_rows[0]]["Case ID"])
    return None
