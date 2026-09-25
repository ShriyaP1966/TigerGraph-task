"""Validates a submission answer file against the exact
format the dataset README defines — the "Answer Format" section of
DATASET_README.md (fields, enums, and the cross-field rules it states explicitly:
legitimate verdicts must have empty affected_txn_ids/zero exposure/no SAR,
sar.file must agree with whether FILE_REPORT appears in the final actions,
approval routes must match the policy's routing table, etc.).

This checks FORMAT and INTERNAL CONSISTENCY, not investigative correctness
— it can't tell you whether the verdict is right, only whether the answer
file is shaped the way the graders expect and doesn't contradict itself.

Also cross-checks case_id against case_pack.csv and similar_prior_cases
entries against closed_cases_history.csv, since both are already in this
repo and let us catch a made-up ID before submission (DATASET_README.md: "IDs must
be the ones in the dataset. Made-up IDs score zero.").

Usage:
    python scripts/validate_answer_file.py cases/HHG-001.json
    python scripts/validate_answer_file.py cases/            # validates every *.json in the folder
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CASE_PACK_PATH = REPO_ROOT / "case_pack.csv"
CLOSED_CASES_PATH = REPO_ROOT / "closed_cases_history.csv"

STATUS_VALUES = {"open", "closed_fraud", "closed_legitimate", "escalated"}
VERDICT_VALUES = {"fraud", "legitimate", "uncertain"}
PATTERN_VALUES = {
    "card_testing",
    "card_not_present_fraud",
    "card_not_present_new_device",
    "out_of_region_use",
    "account_takeover",
    "undocumented",
    "none",
}
EVIDENCE_SOURCE_VALUES = {"graph", "document", "customer", "external"}
EVIDENCE_REQUEST_TYPE_VALUES = {"customer_validation", "step_up_auth", "analyst_info"}
ROUTE_VALUES = {"auto", "L1", "L2"}

# Policy section 2 (DATASET_README.md "Fraud Policy" -> "2. Approval routing").
AUTO_ONLY_ACTIONS = {
    "ALLOW_TRANSACTION",
    "MONITOR_CARD",
    "MONITOR_CONNECTED_CARDS",
    "WARN_CUSTOMER",
    "VERIFY_WITH_CUSTOMER",
    "STEP_UP_AUTH",
    "GENERATE_REPORT",
    "CREATE_CASE",
    "ESCALATE_TO_ANALYST",
    "CLOSE_NO_FRAUD",
}
KNOWN_ACTIONS = AUTO_ONLY_ACTIONS | {"DECLINE_TRANSACTION", "BLOCK_CARD", "BLOCK_ALL_CARDS", "FILE_REPORT"}
BLOCK_CARD_EXPOSURE_THRESHOLD = 2500  # L1 at/under this, L2 above (policy 2)


def _load_case_pack_ids() -> set[str]:
    if not CASE_PACK_PATH.exists():
        return set()
    with CASE_PACK_PATH.open(encoding="utf-8") as f:
        return {row["case_id"] for row in csv.DictReader(f)}


def _load_closed_case_ids() -> set[str]:
    if not CLOSED_CASES_PATH.exists():
        return set()
    with CLOSED_CASES_PATH.open(encoding="utf-8") as f:
        return {row["case_id"] for row in csv.DictReader(f)}


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_str(v: Any) -> bool:
    return isinstance(v, str)


def _is_list_of_str(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def _check_action_list(actions: Any, path: str, exposure_usd: Any, errors: list[str]) -> None:
    if not isinstance(actions, list):
        errors.append(f"{path}: must be a list")
        return
    for i, entry in enumerate(actions):
        p = f"{path}[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{p}: must be an object with action/route/reason")
            continue
        action = entry.get("action")
        route = entry.get("route")
        if action not in KNOWN_ACTIONS:
            errors.append(f"{p}.action: {action!r} is not one of the policy's action identifiers")
        if route not in ROUTE_VALUES:
            errors.append(f"{p}.route: {route!r} must be one of {sorted(ROUTE_VALUES)}")
        if not _is_str(entry.get("reason")) or not entry.get("reason"):
            errors.append(f"{p}.reason: must be a non-empty string citing the policy rule")

        if action in AUTO_ONLY_ACTIONS and route != "auto":
            errors.append(f"{p}: {action} must have route 'auto' per policy section 2, got {route!r}")
        elif action == "DECLINE_TRANSACTION" and route != "L1":
            errors.append(f"{p}: DECLINE_TRANSACTION must have route 'L1' per policy section 2, got {route!r}")
        elif action in ("BLOCK_ALL_CARDS", "FILE_REPORT") and route != "L2":
            errors.append(f"{p}: {action} must have route 'L2' per policy section 2, got {route!r}")
        elif action == "BLOCK_CARD" and _is_number(exposure_usd):
            expected = "L1" if exposure_usd <= BLOCK_CARD_EXPOSURE_THRESHOLD else "L2"
            if route != expected:
                errors.append(
                    f"{p}: BLOCK_CARD with exposure_usd={exposure_usd} must have route {expected!r} "
                    f"per policy section 2 (threshold ${BLOCK_CARD_EXPOSURE_THRESHOLD}), got {route!r}"
                )


def validate_answer(data: dict[str, Any], known_case_ids: set[str], known_closed_case_ids: set[str]) -> list[str]:
    errors: list[str] = []

    for key in ("case_id", "case", "evidence_requests", "next_best_actions", "sar", "stop_reason", "tool_calls", "tokens", "latency_s"):
        if key not in data:
            errors.append(f"top level: missing required field '{key}'")

    case_id = data.get("case_id")
    if _is_str(case_id) and known_case_ids and case_id not in known_case_ids:
        errors.append(f"case_id: {case_id!r} is not one of the 20 case_pack.csv case IDs (made-up IDs score zero)")

    case = data.get("case")
    if not isinstance(case, dict):
        errors.append("case: missing or not an object — skipping case-level checks")
        case = {}
    else:
        for key in (
            "status", "verdict", "fraud_probability", "pattern", "pattern_description",
            "affected_txn_ids", "first_suspicious_txn_id", "connected_card_ids",
            "connected_device_profiles", "exposure_usd", "evidence", "similar_prior_cases",
            "summary", "written_to_graph", "graph_case_id",
        ):
            if key not in case:
                errors.append(f"case: missing required field '{key}'")

        status = case.get("status")
        if status is not None and status not in STATUS_VALUES:
            errors.append(f"case.status: {status!r} must be one of {sorted(STATUS_VALUES)}")

        verdict = case.get("verdict")
        if verdict is not None and verdict not in VERDICT_VALUES:
            errors.append(f"case.verdict: {verdict!r} must be one of {sorted(VERDICT_VALUES)}")

        prob = case.get("fraud_probability")
        if prob is not None and not (_is_number(prob) and 0 <= prob <= 1):
            errors.append(f"case.fraud_probability: {prob!r} must be a number between 0 and 1")

        pattern = case.get("pattern")
        if pattern is not None and pattern not in PATTERN_VALUES:
            errors.append(f"case.pattern: {pattern!r} must be one of {sorted(PATTERN_VALUES)}")

        pattern_desc = case.get("pattern_description")
        if pattern == "undocumented" and not (_is_str(pattern_desc) and pattern_desc.strip()):
            errors.append("case.pattern_description: required (non-empty) when pattern is 'undocumented'")
        elif pattern is not None and pattern != "undocumented" and pattern_desc not in (None, ""):
            errors.append(f'case.pattern_description: must be "" when pattern is not "undocumented", got {pattern_desc!r}')

        affected = case.get("affected_txn_ids")
        if affected is not None and not _is_list_of_str(affected):
            errors.append("case.affected_txn_ids: must be a list of strings")

        exposure = case.get("exposure_usd")
        if exposure is not None and not _is_number(exposure):
            errors.append(f"case.exposure_usd: {exposure!r} must be a number")

        if verdict == "legitimate":
            if affected not in (None, []):
                errors.append("case.affected_txn_ids: must be empty when verdict is 'legitimate'")
            if exposure not in (None, 0, 0.0):
                errors.append(f"case.exposure_usd: must be 0 when verdict is 'legitimate', got {exposure!r}")

        evidence = case.get("evidence")
        if evidence is not None:
            if not isinstance(evidence, list):
                errors.append("case.evidence: must be a list")
            else:
                for i, ev in enumerate(evidence):
                    p = f"case.evidence[{i}]"
                    if not isinstance(ev, dict):
                        errors.append(f"{p}: must be an object")
                        continue
                    if not _is_str(ev.get("claim")) or not ev.get("claim"):
                        errors.append(f"{p}.claim: must be a non-empty string")
                    if ev.get("source") not in EVIDENCE_SOURCE_VALUES:
                        errors.append(f"{p}.source: {ev.get('source')!r} must be one of {sorted(EVIDENCE_SOURCE_VALUES)}")
                    if not _is_str(ev.get("ref")):
                        errors.append(f"{p}.ref: must be a string")
                    if not _is_list_of_str(ev.get("entity_ids")):
                        errors.append(f"{p}.entity_ids: must be a list of strings")

        similar = case.get("similar_prior_cases")
        if similar is not None:
            if not _is_list_of_str(similar):
                errors.append("case.similar_prior_cases: must be a list of strings")
            elif known_closed_case_ids:
                for cc_id in similar:
                    if cc_id not in known_closed_case_ids:
                        errors.append(
                            f"case.similar_prior_cases: {cc_id!r} is not a case_id in closed_cases_history.csv (made-up IDs score zero)"
                        )

        if case.get("written_to_graph") is not None and not isinstance(case.get("written_to_graph"), bool):
            errors.append("case.written_to_graph: must be a boolean")

    sar = data.get("sar")
    if not isinstance(sar, dict):
        errors.append("sar: missing or not an object — skipping SAR checks")
        sar = {}
    else:
        if "file" not in sar or not isinstance(sar.get("file"), bool):
            errors.append("sar.file: required, must be a boolean")
        file_flag = sar.get("file")

        final_actions = ((data.get("next_best_actions") or {}).get("final")) or []
        final_action_names = {a.get("action") for a in final_actions if isinstance(a, dict)}
        if isinstance(file_flag, bool):
            files_report = "FILE_REPORT" in final_action_names
            if file_flag != files_report:
                errors.append(
                    f"sar.file={file_flag} does not agree with whether FILE_REPORT appears in "
                    f"next_best_actions.final (DATASET_README.md: 'Must agree with whether FILE_REPORT appears in your final actions')"
                )

        if file_flag is True:
            if not (_is_str(sar.get("narrative")) and sar.get("narrative", "").strip()):
                errors.append("sar.narrative: required (non-empty) when sar.file is true")
            if not (isinstance(sar.get("subjects"), list) and sar.get("subjects")):
                errors.append("sar.subjects: required (non-empty list) when sar.file is true")
            if not _is_number(sar.get("total_amount_usd")):
                errors.append("sar.total_amount_usd: must be a number when sar.file is true")
            dates = sar.get("activity_dates")
            if not (isinstance(dates, list) and len(dates) == 2 and all(_is_str(d) for d in dates)):
                errors.append("sar.activity_dates: must be a list of exactly two date strings when sar.file is true")
        elif file_flag is False:
            if sar.get("narrative") not in (None, ""):
                errors.append('sar.narrative: must be "" when sar.file is false')
            if sar.get("subjects") not in (None, []):
                errors.append("sar.subjects: must be [] when sar.file is false")
            if sar.get("total_amount_usd") not in (None, 0, 0.0):
                errors.append("sar.total_amount_usd: must be 0 when sar.file is false")
            if sar.get("activity_dates") not in (None, []):
                errors.append("sar.activity_dates: must be [] when sar.file is false")

    nba = data.get("next_best_actions")
    if not isinstance(nba, dict):
        errors.append("next_best_actions: missing or not an object — skipping NBA checks")
    else:
        exposure_usd = (case or {}).get("exposure_usd")
        if "initial" not in nba:
            errors.append("next_best_actions.initial: required")
        else:
            _check_action_list(nba.get("initial"), "next_best_actions.initial", exposure_usd, errors)
        if "final" not in nba:
            errors.append("next_best_actions.final: required")
        else:
            _check_action_list(nba.get("final"), "next_best_actions.final", exposure_usd, errors)
        if not _is_str(nba.get("what_changed")) or not nba.get("what_changed"):
            errors.append('next_best_actions.what_changed: must be a non-empty string (use "nothing" if unchanged)')

    requests = data.get("evidence_requests")
    if requests is not None:
        if not isinstance(requests, list):
            errors.append("evidence_requests: must be a list")
        else:
            for i, r in enumerate(requests):
                p = f"evidence_requests[{i}]"
                if not isinstance(r, dict):
                    errors.append(f"{p}: must be an object")
                    continue
                if r.get("type") not in EVIDENCE_REQUEST_TYPE_VALUES:
                    errors.append(f"{p}.type: {r.get('type')!r} must be one of {sorted(EVIDENCE_REQUEST_TYPE_VALUES)}")
                if not isinstance(r.get("asked_after_step"), int) or isinstance(r.get("asked_after_step"), bool):
                    errors.append(f"{p}.asked_after_step: must be an integer")
                if not _is_str(r.get("assumed_response")) or not r.get("assumed_response"):
                    errors.append(f"{p}.assumed_response: must be a non-empty string")

    if "stop_reason" in data and (not _is_str(data.get("stop_reason")) or not data.get("stop_reason")):
        errors.append("stop_reason: must be a non-empty string")
    if "tool_calls" in data and not (isinstance(data.get("tool_calls"), int) and not isinstance(data.get("tool_calls"), bool)):
        errors.append("tool_calls: must be an integer")
    if "tokens" in data and not (isinstance(data.get("tokens"), int) and not isinstance(data.get("tokens"), bool)):
        errors.append("tokens: must be an integer")
    if "latency_s" in data and not _is_number(data.get("latency_s")):
        errors.append("latency_s: must be a number")

    return errors


def _iter_target_files(target: Path) -> list[Path]:
    if target.is_dir():
        return sorted(target.glob("*.json"))
    return [target]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    target = Path(sys.argv[1])
    if not target.exists():
        print(f"Path not found: {target}")
        return 2

    known_case_ids = _load_case_pack_ids()
    known_closed_case_ids = _load_closed_case_ids()
    if not known_case_ids:
        print(f"Warning: {CASE_PACK_PATH} not found — skipping case_id cross-checks.")
    if not known_closed_case_ids:
        print(f"Warning: {CLOSED_CASES_PATH} not found — skipping similar_prior_cases cross-checks.")

    files = _iter_target_files(target)
    if not files:
        print(f"No .json files found at {target}")
        return 2

    total_errors = 0
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"[FAIL] {f.name}: invalid JSON — {e}")
            total_errors += 1
            continue

        errors = validate_answer(data, known_case_ids, known_closed_case_ids)
        if errors:
            print(f"[FAIL] {f.name}: {len(errors)} issue(s)")
            for e in errors:
                print(f"    - {e}")
            total_errors += len(errors)
        else:
            print(f"[PASS] {f.name}")

    print()
    if total_errors:
        print(f"{total_errors} total issue(s) across {len(files)} file(s).")
        return 1
    print(f"All {len(files)} file(s) passed format validation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
