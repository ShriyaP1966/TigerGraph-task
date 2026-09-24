"""
MCP tool implementations backing /contracts/mcp_tool_contracts.json.

Supports:
  - fixture mode: returns realistic example data
  - live mode: connects to TigerGraph Cloud using a GSQL secret
"""

from __future__ import annotations

from typing import Optional

from . import config

_conn = None


# ============================================================================
# TigerGraph connection
# ============================================================================

def _get_connection():
    """
    Create and cache a TigerGraph Cloud connection.

    TigerGraph Cloud authentication uses the GSQL secret.
    The secret is exchanged for an API token by pyTigerGraph.
    """
    global _conn

    if _conn is not None:
        return _conn

    import pyTigerGraph as tg

    if not config.TG_SECRET:
        raise RuntimeError(
            "TG_SECRET is missing. Set the TigerGraph Cloud GSQL secret."
        )

    if not config.TG_HOST:
        raise RuntimeError(
            "TG_HOST is missing. Set the TigerGraph Cloud host URL."
        )

    # Ensure the host starts with https:// for TigerGraph Cloud
    host = config.TG_HOST
    if not host.startswith("http://") and not host.startswith("https://"):
        host = f"https://{host}"

    print(f"[MCP] Connecting to TigerGraph Cloud at {host} (graph: {config.TG_GRAPH})...")

    _conn = tg.TigerGraphConnection(
        host=host,
        graphname=config.TG_GRAPH,
        gsqlSecret=config.TG_SECRET,
    )

    # Exchange the GSQL secret for an API token.
    try:
        _conn.getToken(config.TG_SECRET)
        print("[MCP] TigerGraph authentication successful.")
    except Exception as e:
        print(f"[MCP] TigerGraph authentication FAILED: {e}")
        raise

    return _conn


def _live_mode() -> bool:
    return config.MCP_MODE.lower() == "live"


# ============================================================================
# 1. get_account_subgraph
# ============================================================================

def get_account_subgraph(
    card_id: str,
    txn_limit: int = 100,
    include_shared_links: bool = True,
) -> dict:

    if not _live_mode():
        return _FIXTURES["get_account_subgraph"]

    conn = _get_connection()

    result = conn.runInstalledQuery(
        "get_account_subgraph",
        params={
            "seed_card": (card_id,),
            "txn_limit": txn_limit,
        },
    )

    # The installed query PRINTs seed_card as a bare vertex id string, not a
    # vertex set, so there are no card attributes here (card_id is known anyway).
    card_v = (
        result[0].get("seed_card", {})
        if result
        else {}
    )
    if not isinstance(card_v, dict):
        card_v = {}

    owner_v = (
        (result[1].get("Owner") or [{}])[0]
        if len(result) > 1
        else {}
    )

    txns = (
        result[2].get("RecentTxns", [])
        if len(result) > 2
        else []
    )

    shared = (
        result[3]
        if len(result) > 3
        else {}
    )

    shared_links = []

    if include_shared_links:

        for link_type, key in [
            ("SHARES_DEVICE", "DeviceLinks"),
            ("SHARES_EMAIL", "EmailLinks"),
            ("SHARES_ADDRESS", "AddressLinks"),
        ]:

            for v in shared.get(key, []):

                shared_links.append({
                    "linked_card_id": v.get(
                        "v_id",
                        v.get("card_id", "")
                    ),
                    "link_type": link_type,
                    "shared_value": "",
                })

    attributes = card_v.get("attributes", {})

    return {
        "card": {
            "card_id": card_id,
            "customer_id": attributes.get(
                "customer_id",
                ""
            ),
            "network": attributes.get(
                "network",
                ""
            ),
            "card_type": attributes.get(
                "card_type",
                ""
            ),
        },

        "customer": {
            "customer_id": owner_v.get(
                "v_id",
                ""
            )
        },

        "transactions": [
            _txn_from_vertex(t)
            for t in txns
        ],

        "shared_links": shared_links,
    }


def _txn_from_vertex(v: dict) -> dict:

    attributes = v.get(
        "attributes",
        v
    )

    return {
        "txn_id": v.get(
            "v_id",
            attributes.get("txn_id", "")
        ),

        "ts": attributes.get(
            "ts",
            ""
        ),

        "amount": attributes.get(
            "amount",
            0
        ),

        "product_cd": attributes.get(
            "product_cd",
            ""
        ),

        "channel": attributes.get(
            "channel",
            ""
        ),

        "risk_score": attributes.get(
            "risk_score",
            0
        ),

        "addr1": attributes.get(
            "addr1",
            ""
        ),

        "addr2": attributes.get(
            "addr2",
            ""
        ),

        "p_email_domain": attributes.get(
            "p_email_domain",
            ""
        ),

        "r_email_domain": attributes.get(
            "r_email_domain",
            ""
        ),

        "device_id": attributes.get(
            "device_id"
        ) or None,
    }


# ============================================================================
# 2. find_fraud_ring
# ============================================================================

def find_fraud_ring(
    card_id: str,
    max_hops: int = 3,
    min_shared_weight: int = 1,
) -> dict:

    if not _live_mode():
        return _FIXTURES["find_fraud_ring"]

    conn = _get_connection()

    result = conn.runInstalledQuery(
        "find_fraud_ring",
        params={
            "seed_card": (card_id,),
            "max_hops": max_hops,
        },
    )

    cluster_rows = (
        result[0].get("Cluster", [])
        if result
        else []
    )

    shared_groups = (
        result[1].get(
            "shared_attributes",
            {}
        )
        if len(result) > 1
        else {}
    )

    cards = []

    for row in cluster_rows:

        attributes = row.get(
            "attributes",
            {}
        )

        cards.append({
            "card_id": row.get(
                "v_id"
            ),

            "customer_id": attributes.get(
                "customer_id",
                ""
            ),

            "hop_distance": attributes.get(
                "@hop_distance",
                0
            ),
        })

    shared_attributes = []

    for key, card_ids in shared_groups.items():

        if ":" not in key:
            continue

        type_, value = key.split(
            ":",
            1
        )

        if len(card_ids) < (
            min_shared_weight + 1
        ):
            continue

        shared_attributes.append({
            "type": type_,
            "value": value,
            "card_ids": list(card_ids),
        })

    return {
        "cluster_id": f"RING-{card_id}",
        "cards": cards,
        "shared_attributes": shared_attributes,
        "cluster_size": len(cards),
    }


# ============================================================================
# 3. get_transaction_velocity
# ============================================================================

def get_transaction_velocity(
    card_id: str,
    window_minutes: int,
    reference_txn_id: str = "",
    amount_threshold: Optional[float] = None,
) -> dict:

    if not _live_mode():
        return _FIXTURES["get_transaction_velocity"]

    conn = _get_connection()

    result = conn.runInstalledQuery(
        "get_transaction_velocity",
        params={
            "seed_card": (card_id,),
            "window_minutes": window_minutes,
            "reference_txn_id": reference_txn_id,
            "amount_threshold": (
                amount_threshold
                if amount_threshold is not None
                else -1
            ),
        },
    )

    row = (
        result[0]
        if result
        else {}
    )

    return {
        "card_id": card_id,
        "window_minutes": window_minutes,

        "txn_count": row.get(
            "txn_count",
            0
        ),

        "txn_sum": row.get(
            "txn_sum",
            0.0
        ),

        "small_txn_count": (
            row.get("small_txn_count")
            if amount_threshold is not None
            else None
        ),

        "txn_ids": row.get(
            "txn_ids",
            []
        ),
    }


# ============================================================================
# 4. get_prior_similar_cases
# ============================================================================

def get_prior_similar_cases(
    card_id: str = "",
    device_id: str = "",
    pattern: str = "",
    query_text: str = "",
    top_k: int = 5,
) -> dict:

    if not _live_mode():
        return _FIXTURES["get_prior_similar_cases"]

    conn = _get_connection()

    result = conn.runInstalledQuery(
        "get_prior_similar_cases",
        params={
            "seed_card": (
                (card_id,)
                if card_id
                else ""
            ),
            "pattern_filter": pattern,
            "top_k": top_k,
        },
    )

    rows = (
        result[0].get(
            "Result",
            []
        )
        if result
        else []
    )

    cases = []

    for row in rows:

        attributes = row.get(
            "attributes",
            {}
        )

        cases.append({
            "case_id": row.get(
                "v_id"
            ),

            "outcome": attributes.get(
                "outcome",
                ""
            ),

            "pattern": attributes.get(
                "pattern",
                ""
            ),

            "exposure_usd": attributes.get(
                "exposure_usd",
                0
            ),

            "analyst_notes": attributes.get(
                "analyst_notes",
                ""
            ),

            "match_reason":
                "shared device/region/email or direct card match",

            "similarity_score": 0.75,
        })

    return {
        "similar_cases": cases[:top_k]
    }


# ============================================================================
# 5. get_policy_context
# ============================================================================

def get_policy_context(
    topic: str
) -> dict:

    if not _live_mode():
        return _FIXTURES["get_policy_context"]

    conn = _get_connection()

    result = conn.runInstalledQuery(
        "get_policy_context",
        params={
            "topic": topic
        },
    )

    clauses = (
        result[0].get(
            "Clauses",
            []
        )
        if result
        else []
    )

    typologies = (
        result[1].get(
            "Typologies",
            []
        )
        if len(result) > 1
        else []
    )

    return {
        "policy_clauses": [
            {
                "clause_id": c.get(
                    "v_id"
                ),

                "text": c.get(
                    "attributes",
                    {}
                ).get(
                    "text",
                    ""
                ),
            }

            for c in clauses
        ],

        "typologies": [
            {
                "typology_id": t.get(
                    "v_id"
                ),

                "description": t.get(
                    "attributes",
                    {}
                ).get(
                    "description",
                    ""
                ),
            }

            for t in typologies
        ],
    }


# ============================================================================
# 6. shortest_path_between_cards
# ============================================================================

def shortest_path_between_cards(
    card_id_a: str,
    card_id_b: str,
    max_hops: int = 6,
) -> dict:

    if not _live_mode():
        return _FIXTURES[
            "shortest_path_between_cards"
        ]

    conn = _get_connection()

    result = conn.runInstalledQuery(
        "shortest_path_between_cards",
        params={
            "card_a": card_id_a,
            "card_b": card_id_b,
            "max_hops": max_hops,
        },
    )

    found = (
        result[0].get(
            "found",
            False
        )
        if result
        else False
    )

    if not found:

        return {
            "found": False,
            "path": [],
            "link_types": [],
        }

    parent_map = (
        result[1].get(
            "parent_map",
            {}
        )
        if len(result) > 1
        else {}
    )

    path = [card_id_b]

    current = card_id_b

    seen = {
        current
    }

    while (
        current in parent_map
        and current != card_id_a
    ):

        current = parent_map[
            current
        ]

        if current in seen:
            break

        seen.add(current)

        path.append(current)

    path.reverse()

    return {
        "found": True,

        "path": [
            {
                "card_id": card
            }

            for card in path
        ],

        "link_types": [],
    }


# ============================================================================
# 7. write_case_to_graph
# ============================================================================

def write_case_to_graph(
    case_id: str,
    case: dict,
    next_best_actions: dict,
    sar: Optional[dict] = None,
) -> dict:

    if not _live_mode():

        return {
            "graph_case_id":
                f"CASE-FIXTURE-{case_id}",

            "written": False,

            "similar_to_edges_created": 0,

            "note":
                "MCP_MODE=fixture -- nothing was actually written. "
                "Switch to live once TigerGraph is up.",
        }

    conn = _get_connection()

    graph_case_id = (
        f"CASE-{case_id}"
    )

    # KNOWN GAP (accepted for the 2026-09-24 submission run): the installed
    # write_case_to_graph query takes no evidence_list / action_list params,
    # so Evidence, HAS_EVIDENCE and RECOMMENDS are NOT written to the graph.
    # Evidence and actions still live in the case JSON and local memory.
    # Actions are still collected below only to extract cited clause IDs.

    action_list = []

    for phase in (
        "initial",
        "final",
    ):

        for action in next_best_actions.get(
            phase,
            []
        ):

            action_list.append({
                "action_name": action[
                    "action"
                ],

                "phase": phase,

                "route": action[
                    "route"
                ],

                "reason": action[
                    "reason"
                ],
            })

    cited_clauses = set()

    import re

    for action in action_list:

        for match in re.findall(
            r"\bR\d{1,2}\b",
            action["reason"],
        ):

            cited_clauses.add(
                match
            )

    result = conn.runInstalledQuery(
        "write_case_to_graph",
        params={
            "graph_case_id":
                graph_case_id,

            "case_pack_id":
                case_id,

            "status":
                case.get(
                    "status",
                    ""
                ),

            "verdict":
                case.get(
                    "verdict",
                    ""
                ),

            "fraud_probability":
                case.get(
                    "fraud_probability",
                    0.0
                ),

            "pattern":
                case.get(
                    "pattern",
                    "none"
                ),

            "pattern_description":
                case.get(
                    "pattern_description",
                    ""
                ),

            "exposure_usd":
                case.get(
                    "exposure_usd",
                    0.0
                ),

            "first_suspicious_txn_id":
                case.get(
                    "first_suspicious_txn_id",
                    ""
                ),

            "summary":
                case.get(
                    "summary",
                    ""
                ),

            "stop_reason":
                case.get(
                    "stop_reason",
                    ""
                ),

            "customer_id_involved":
                "",

            "affected_txn_ids":
                case.get(
                    "affected_txn_ids",
                    []
                ),

            "connected_card_ids":
                case.get(
                    "connected_card_ids",
                    []
                ),

            "similar_prior_case_ids":
                case.get(
                    "similar_prior_cases",
                    []
                ),

            "cited_clause_ids":
                list(cited_clauses),
        },
    )

    row = (
        result[0]
        if result
        else {}
    )

    return {
        "graph_case_id":
            row.get(
                "graph_case_id",
                graph_case_id
            ),

        "written":
            row.get(
                "written",
                True
            ),

        "similar_to_edges_created":
            row.get(
                "similar_to_edges_created",
                0
            ),
    }


# ============================================================================
# Fixtures
# ============================================================================

_FIXTURES = {

    "get_account_subgraph": {

        "card": {
            "card_id": "C12382-K1",
            "customer_id": "C12382",
            "network": "visa",
            "card_type": "credit",
        },

        "customer": {
            "customer_id": "C12382"
        },

        "transactions": [

            {
                "txn_id": "3514030",
                "ts": "2016-12-05T01:55:28",
                "amount": 77.07,
                "product_cd": "W",
                "channel": "in_person",
                "risk_score": 0.61,
                "addr1": "444.0",
                "addr2": "87.0",
                "p_email_domain": "gmail.com",
                "r_email_domain": "",
                "device_id": None,
            }

        ],

        "shared_links": [],
    },


    "find_fraud_ring": {

        "cluster_id":
            "RING-C08623-K2",

        "cards": [

            {
                "card_id":
                    "C08623-K2",

                "customer_id":
                    "C08623",

                "hop_distance":
                    0,
            },

            {
                "card_id":
                    "C08877-K1",

                "customer_id":
                    "C08877",

                "hop_distance":
                    1,
            },

        ],

        "shared_attributes": [

            {
                "type":
                    "device",

                "value":
                    "SAMSUNG SM-G935F Build/NRD90M|Android 7.0|samsung browser 6.2|2220x1080",

                "card_ids": [
                    "C08623-K2",
                    "C08877-K1",
                ],
            },

        ],

        "cluster_size":
            2,
    },


    "get_transaction_velocity": {

        "card_id":
            "C08623-K2",

        "window_minutes":
            60,

        "txn_count":
            4,

        "txn_sum":
            268.43,

        "small_txn_count":
            3,

        "txn_ids": [
            "T0412877",
            "T0412878",
            "T0412879",
            "T0412883",
        ],
    },


    "get_prior_similar_cases": {

        "similar_cases": [

            {
                "case_id":
                    "CC-0141",

                "outcome":
                    "confirmed_fraud",

                "pattern":
                    "card_testing",

                "exposure_usd":
                    312.5,

                "analyst_notes":
                    "Device profile New-for-account, three sub-$3 auths then a larger purchase.",

                "match_reason":
                    "shared device profile",

                "similarity_score":
                    0.87,
            },

        ],
    },


    "get_policy_context": {

        "policy_clauses": [

            {
                "clause_id":
                    "R5",

                "text":
                    "Card testing. Three or more small online authorizations on one card within an hour, followed by a larger purchase: recommend DECLINE_TRANSACTION and STEP_UP_AUTH. If a purchase over $100 has already cleared, recommend BLOCK_CARD.",
            },

        ],

        "typologies": [

            {
                "typology_id":
                    "card_testing",

                "description":
                    "A stolen card number is checked before use: three or more tiny online authorizations, often under $5, then a larger purchase.",
            },

        ],
    },


    "shortest_path_between_cards": {

        "found":
            True,

        "path": [

            {
                "card_id":
                    "C08623-K2"
            },

            {
                "card_id":
                    "C08877-K1"
            },

        ],

        "link_types": [
            "SHARES_DEVICE"
        ],
    },

}