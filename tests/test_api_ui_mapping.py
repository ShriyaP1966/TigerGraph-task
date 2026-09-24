"""Regression coverage for api.py's UI mapping: catches action-enum values that don't
exist in case_record_schema.json (e.g. lowercasing BLOCK_CARD gives "block_card", which
isn't a valid decisions_and_actions[].action) and get_case()'s reload path losing
trigger/customer_id info that isn't in the Answer Format itself."""
import json
import os
import sys
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("GRAPH_BACKEND", "mock")
os.environ.setdefault("LLM_MODE", "fixture")

import api

SCHEMA = json.loads((REPO_ROOT / "contracts" / "case_record_schema.json").read_text(encoding="utf-8"))

TRIGGER = {
    "case_id": "TEST-API-001",
    "opened_at": "2016-12-05 01:55:28",
    "trigger_type": "risk_score",
    "trigger_text": "test trigger",
    "flagged_txn_id": "T900004",
    "card_id": "ACCT-RING-1-K1",
    "customer_id": "ACCT-RING-1",
    "risk_score": 0.61,
}


def test_run_case_matches_ui_schema():
    ui_dict = api.run_case(TRIGGER)
    jsonschema.validate(ui_dict, SCHEMA)
    for d in ui_dict["decisions_and_actions"]:
        assert d["action"] in SCHEMA["properties"]["decisions_and_actions"]["items"]["properties"]["action"]["enum"]


def test_get_case_matches_ui_schema():
    reloaded = api.get_case("TEST-API-001")
    assert reloaded is not None
    jsonschema.validate(reloaded, SCHEMA)
    assert reloaded["trigger"]["type"] in ("risk_score", "customer_report", "analyst_request")


if __name__ == "__main__":
    test_run_case_matches_ui_schema()
    test_get_case_matches_ui_schema()
    (REPO_ROOT / "cases" / "TEST-API-001.json").unlink(missing_ok=True)
    print("api.py UI mapping matches case_record_schema.json")
