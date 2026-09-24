from langgraph.graph import END, StateGraph

from agent import nodes
from agent.state import CaseState, new_state


def build_graph():
    g = StateGraph(CaseState)
    for name, fn in [
        ("trigger_intake", nodes.trigger_intake),
        ("open_or_load_case", nodes.open_or_load_case),
        ("gather_graph_evidence", nodes.gather_graph_evidence),
        ("gather_graphrag_context", nodes.gather_graphrag_context),
        ("assess_patterns_and_risk", nodes.assess_patterns_and_risk),
        ("uncertainty_gate", nodes.uncertainty_gate),
        ("request_more_evidence", nodes.request_more_evidence),
        ("decide_actions", nodes.decide_actions),
        ("approval_gate", nodes.approval_gate),
        ("execute_or_record", nodes.execute_or_record),
        ("explain", nodes.explain),
        ("update_case_memory", nodes.update_case_memory),
    ]:
        g.add_node(name, fn)

    g.set_entry_point("trigger_intake")
    g.add_edge("trigger_intake", "open_or_load_case")
    g.add_edge("open_or_load_case", "gather_graph_evidence")
    g.add_edge("gather_graph_evidence", "gather_graphrag_context")
    g.add_edge("gather_graphrag_context", "assess_patterns_and_risk")
    g.add_edge("assess_patterns_and_risk", "uncertainty_gate")
    g.add_conditional_edges("uncertainty_gate", nodes.route_after_uncertainty, {"request_more_evidence": "request_more_evidence", "decide_actions": "decide_actions"})
    g.add_edge("request_more_evidence", "assess_patterns_and_risk")
    g.add_edge("decide_actions", "approval_gate")
    g.add_edge("approval_gate", "execute_or_record")
    g.add_edge("execute_or_record", "explain")
    g.add_edge("explain", "update_case_memory")
    g.add_edge("update_case_memory", END)

    return g.compile()


_GRAPH = None


def run_case(case_row: dict, backend) -> dict:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    state = new_state(case_row, backend)
    return _GRAPH.invoke(state, config={"recursion_limit": 50})
