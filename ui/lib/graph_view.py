"""Case-specific subgraph view.

Builds a graph strictly from what a case record already states
(contracts/case_record_schema.json): `entities` (customer/account/
transaction/device IDs), `investigation_record.fraud_pattern_identified`,
and `case_memory.similar_prior_cases_used`. Nothing is inferred beyond
those fields — e.g. the schema does not say which transaction belongs to
which account, so every transaction links to the case itself rather than to
a guessed account.

Edge labels follow the graph data model
(FraudCase -INVOLVES-> Transaction/Account/Customer, -MATCHES-> FraudTypology,
-SIMILAR_TO-> FraudCase), so this preview lines up with what's
loaded into TigerGraph.
"""

from __future__ import annotations

from typing import Any

import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

_NODE_COLOR = {
    "case": "#2a78d6",
    "customer": "#1baf7a",
    "account": "#eda100",
    "transaction": "#898781",
    "device": "#4a3aa7",
    "typology": "#d03b3b",
    "similar_case": "#e87ba4",
}

_NODE_SIZE = {
    "case": 28,
    "customer": 22,
    "account": 18,
    "transaction": 13,
    "device": 18,
    "typology": 18,
    "similar_case": 16,
}


def build_case_graph(case: dict[str, Any]) -> tuple[list[Node], list[Edge]]:
    entities = case.get("entities", {}) or {}
    case_id = case["case_id"]

    nodes: dict[str, Node] = {}
    edges: list[Edge] = []

    def add_node(node_id: str, kind: str) -> None:
        if node_id in nodes:
            return
        nodes[node_id] = Node(
            id=node_id,
            label=node_id,
            size=_NODE_SIZE.get(kind, 14),
            color=_NODE_COLOR.get(kind, "#898781"),
            shape="dot",
        )

    add_node(case_id, "case")

    customer_id = entities.get("customer_id")
    if customer_id:
        add_node(customer_id, "customer")
        edges.append(Edge(source=case_id, target=customer_id, label="INVOLVES"))

    for acct_id in entities.get("account_ids") or []:
        add_node(acct_id, "account")
        edges.append(Edge(source=case_id, target=acct_id, label="INVOLVES"))
        if customer_id:
            edges.append(Edge(source=customer_id, target=acct_id, label="OWNS"))

    for txn_id in entities.get("transaction_ids") or []:
        add_node(txn_id, "transaction")
        edges.append(Edge(source=case_id, target=txn_id, label="INVOLVES"))

    for dev_id in entities.get("device_ids") or []:
        add_node(dev_id, "device")
        edges.append(Edge(source=case_id, target=dev_id, label="FLAGGED_DEVICE"))

    pattern = (case.get("investigation_record") or {}).get("fraud_pattern_identified")
    if pattern:
        add_node(pattern, "typology")
        edges.append(Edge(source=case_id, target=pattern, label="MATCHES"))

    for prior in (case.get("case_memory") or {}).get("similar_prior_cases_used") or []:
        prior_id = prior.get("case_id")
        if not prior_id:
            continue
        add_node(prior_id, "similar_case")
        sim = prior.get("similarity_score")
        label = f"SIMILAR_TO ({sim:.2f})" if isinstance(sim, (int, float)) else "SIMILAR_TO"
        edges.append(Edge(source=case_id, target=prior_id, label=label))

    return list(nodes.values()), edges


def render_case_graph(case: dict[str, Any]) -> None:
    nodes, edges = build_case_graph(case)
    if len(nodes) <= 1:
        st.info("No connected entities recorded for this case yet.")
        return

    legend_bits = " &nbsp;&nbsp; ".join(
        f'<span style="color:{color};">●</span> {kind.replace("_", " ")}'
        for kind, color in _NODE_COLOR.items()
    )
    st.markdown(f'<div class="muted">{legend_bits}</div>', unsafe_allow_html=True)

    config = Config(
        width="100%",
        height=420,
        directed=True,
        physics=True,
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#2a78d6",
        collapsible=False,
        node={"labelProperty": "label"},
        link={"labelProperty": "label", "renderLabel": True},
    )
    agraph(nodes=nodes, edges=edges, config=config)
