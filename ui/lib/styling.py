"""Shared visual language for the dashboard: a validated status palette
(good/warning/serious/critical), a single-hue sequential ramp for magnitude
bars, and badge/CSS helpers. Colors are never the only carrier of meaning —
every badge pairs color with an icon and a text label.
"""

from __future__ import annotations

import html as _html
from typing import Any

STATUS_COLORS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
    "neutral": "#2a78d6",
}

INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
SURFACE = "#fcfcfb"
PAGE_PLANE = "#f9f9f7"
GRIDLINE = "#e1e0d9"
BORDER = "rgba(11,11,11,0.10)"

# Single hue, light -> dark, for magnitude bars (confidence components).
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"]

RISK_LEVEL_STYLE = {
    "low": ("good", "●", "Low risk"),
    "medium": ("warning", "●", "Medium risk"),
    "high": ("critical", "●", "High risk"),
}

CASE_STATUS_STYLE = {
    "open": ("warning", "Open"),
    "gathering_evidence": ("warning", "Gathering evidence"),
    "pending_customer_response": ("warning", "Awaiting customer"),
    "pending_approval": ("warning", "Pending approval"),
    "closed_fraud": ("critical", "Closed — fraud"),
    "closed_cleared": ("good", "Closed — cleared"),
    "closed_monitoring": ("serious", "Closed — monitoring"),
}

DECISION_STATUS_STYLE = {
    "recommended": ("neutral", "Recommended"),
    "pending_approval": ("warning", "Pending approval"),
    "approved": ("good", "Approved"),
    "rejected": ("critical", "Rejected"),
    "executed": ("good", "Executed"),
}


def esc(text: Any) -> str:
    """HTML-escape free text before it goes into an unsafe_allow_html block.

    Case/evidence/rationale/explanation text originates from the agent
    (eventually an LLM) and may contain '<', '>', '&', or quotes — e.g. a
    rationale like "amount < $500" would otherwise be parsed as a stray HTML
    tag and break the layout. Every dynamic string interpolated into an HTML
    template in components/ should be wrapped in this; the template's own
    structural tags (<div>, <br>, ...) are left untouched.
    """
    if text is None:
        return ""
    return _html.escape(str(text))


def sequential_step(value: float) -> str:
    """Map a 0-1 magnitude onto the sequential blue ramp."""
    value = max(0.0, min(1.0, value or 0.0))
    idx = min(len(SEQUENTIAL_BLUE) - 1, int(value * (len(SEQUENTIAL_BLUE) - 1)))
    return SEQUENTIAL_BLUE[idx]


def badge(label: str, role: str, icon: str = "●") -> str:
    """A pill badge: color + icon + label, never color alone.

    `label` may echo a raw enum value straight from case data (the
    fallback path when it isn't one of the known statuses/routes), so it's
    escaped here — the one place every badge* helper funnels through.
    """
    color = STATUS_COLORS.get(role, STATUS_COLORS["neutral"])
    return (
        '<span style="display:inline-flex;align-items:center;gap:6px;'
        f"padding:3px 11px;border-radius:12px;background:{color}1f;"
        f'border:1px solid {color}66;color:{INK_PRIMARY};'
        'font-size:0.82rem;font-weight:600;white-space:nowrap;line-height:1.6;">'
        f'<span style="color:{color};font-size:0.65rem;">{icon}</span>{esc(label)}</span>'
    )


def risk_badge(risk_level: str | None) -> str:
    role, icon, label = RISK_LEVEL_STYLE.get(risk_level or "", ("neutral", "●", risk_level or "unknown"))
    return badge(label, role, icon)


def case_status_badge(status: str | None) -> str:
    role, label = CASE_STATUS_STYLE.get(status or "", ("neutral", status or "unknown"))
    return badge(label, role)


def decision_status_badge(status: str | None) -> str:
    role, label = DECISION_STATUS_STYLE.get(status or "", ("neutral", status or "unknown"))
    return badge(label, role)


def approval_route_badge(route: str | None) -> str:
    role = "good" if route == "auto" else "warning"
    label = {"auto": "Auto", "fraud_analyst": "Fraud analyst", "compliance_officer": "Compliance officer"}.get(
        route or "", route or "unknown"
    )
    return badge(f"Route: {label}", role, "→")


def inject_css() -> str:
    return f"""
    <style>
      html, body, [class*="css"] {{
        font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
      }}
      .block-container {{
        padding-top: 1.6rem;
        max-width: 1400px;
      }}
      h1, h2, h3 {{
        color: {INK_PRIMARY};
        letter-spacing: -0.01em;
      }}
      .case-card {{
        background: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 10px;
      }}
      .section-label {{
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-size: 0.72rem;
        font-weight: 700;
        color: {INK_MUTED};
        margin-bottom: 6px;
      }}
      .evidence-row {{
        border-left: 3px solid {STATUS_COLORS['neutral']};
        padding: 6px 0 6px 14px;
        margin-bottom: 10px;
      }}
      .finding-row {{
        border-left: 3px solid {STATUS_COLORS['serious']};
        padding: 6px 0 6px 14px;
        margin-bottom: 10px;
      }}
      .metric-value {{
        font-size: 2.1rem;
        font-weight: 700;
        color: {INK_PRIMARY};
        font-variant-numeric: tabular-nums;
      }}
      .muted {{
        color: {INK_MUTED};
        font-size: 0.85rem;
      }}
      .secondary-text {{
        color: {INK_SECONDARY};
      }}
      .clause-chip {{
        display: inline-block;
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 1px 8px;
        margin: 2px 4px 2px 0;
        font-size: 0.78rem;
        color: {INK_SECONDARY};
        background: {PAGE_PLANE};
      }}
      hr {{
        border-color: {GRIDLINE};
      }}
    </style>
    """
