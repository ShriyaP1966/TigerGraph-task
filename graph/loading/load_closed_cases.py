"""
Load closed_cases_history.csv into TigerGraph: ClosedCase vertices plus
ON_CARD edges (ClosedCase -> Card), via the REST++ upsert endpoint.

This is the case-memory corpus get_prior_similar_cases retrieves from
(Card <-ON_CARD- ClosedCase). None of the loading jobs in 02_loading_jobs.gsql
cover it, and TigerGraph Cloud's file loader was not set up for it, so it is
loaded over REST instead. Upserts are idempotent: re-running is safe.

ON_CARD edges are only written for cards that already exist in the graph
(vertex_must_exist=true), so a bad card_id is reported as skipped rather than
silently creating an empty Card vertex.

Usage (reads TG_HOST, TG_SECRET, TG_GRAPH_NAME from the environment / .env):
    python graph/loading/load_closed_cases.py [path/to/closed_cases_history.csv]
"""

import csv
import os
import sys

import requests
from dotenv import load_dotenv

BATCH_SIZE = 500


def _token(host: str, secret: str) -> str:
    r = requests.post(f"{host}/gsql/v1/tokens", json={"secret": secret}, timeout=30)
    r.raise_for_status()
    body = r.json()
    if body.get("error"):
        raise RuntimeError(f"token request failed: {body.get('message')}")
    return body["token"]


def _split(value: str) -> list:
    return [v for v in value.split("|") if v] if value else []


def _vertex_attrs(row: dict) -> dict:
    return {
        "customer_id": {"value": row["customer_id"]},
        "card_id": {"value": row["card_id"]},
        "opened_at": {"value": row["opened_at"]},
        "closed_at": {"value": row["closed_at"]},
        "outcome": {"value": row["outcome"]},
        "pattern": {"value": row["pattern"]},
        "first_fraud_txn_id": {"value": row["first_fraud_txn_id"]},
        "txn_ids": {"value": _split(row["txn_ids"])},
        "n_txns": {"value": int(row["n_txns"] or 0)},
        "exposure_usd": {"value": float(row["exposure_usd"] or 0.0)},
        "connected_card_ids": {"value": _split(row["connected_card_ids"])},
        "actions_taken": {"value": row["actions_taken"]},
        "report_filed": {"value": row["report_filed"].strip().lower() == "yes"},
        "analyst_notes": {"value": row["analyst_notes"]},
    }


def main() -> int:
    load_dotenv()
    host = os.environ.get("TG_HOST", "").rstrip("/")
    secret = os.environ.get("TG_SECRET", "")
    graph = os.environ.get("TG_GRAPH_NAME", "FraudGraph")
    if not host or not secret:
        print("TG_HOST and TG_SECRET must be set", file=sys.stderr)
        return 1
    if not host.startswith("http"):
        host = f"https://{host}"

    path = sys.argv[1] if len(sys.argv) > 1 else "closed_cases_history.csv"
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    headers = {"Authorization": f"Bearer {_token(host, secret)}"}
    url = f"{host}/restpp/graph/{graph}"

    vertices = edges = skipped = 0
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start:start + BATCH_SIZE]

        payload = {"vertices": {"ClosedCase": {r["case_id"]: _vertex_attrs(r) for r in batch}}}
        r = requests.post(url, json=payload, headers=headers, timeout=120)
        r.raise_for_status()
        vertices += r.json()["results"][0]["accepted_vertices"]

        payload = {"edges": {"ClosedCase": {
            r["case_id"]: {"ON_CARD": {"Card": {r["card_id"]: {}}}} for r in batch if r["card_id"]
        }}}
        r = requests.post(url, params={"vertex_must_exist": "true"}, json=payload, headers=headers, timeout=120)
        r.raise_for_status()
        result = r.json()["results"][0]
        edges += result["accepted_edges"]
        skipped += result.get("skipped_edges", 0)

        print(f"  {min(start + BATCH_SIZE, len(rows))}/{len(rows)} rows")

    print(f"ClosedCase vertices upserted: {vertices}")
    print(f"ON_CARD edges upserted: {edges} (skipped, card not in graph: {skipped})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
