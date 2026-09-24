"""Runs the agent over case_pack.csv and writes one answer file per case to cases/.

Usage:
    python run_benchmark.py                              # all 20, resume if partially done
    python run_benchmark.py --cases HHG-001,HHG-011       # just these
    python run_benchmark.py --backend local --llm-mode fixture

Case memory (memory/.cache/added_cases.json) persists across runs by design - that's
what lets case N retrieve case N-1 as a similar prior case. For a reproducible from-
scratch grading run, clear it first: rm -f memory/.cache/added_cases.json
memory/.cache/open_cases.json - otherwise leftover cases from a prior partial/test run
shift similarity retrieval (and, downstream, simulate_response's fact-based lean) for
whichever case_pack cases happen to be textually close to them.
"""
import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

CASES_DIR = REPO_ROOT / "cases"


def load_case_pack() -> list[dict]:
    with (REPO_ROOT / "case_pack.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # chronological, not file order - case memory is time-aware (get_prior_similar_cases
    # filters by opened_at), so processing out of order makes case N's available memory
    # depend on which cases happened to run before it rather than what actually happened
    # before it in the story, which is both wrong and non-deterministic across reruns
    return sorted(rows, key=lambda r: r["opened_at"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default=os.environ.get("GRAPH_BACKEND", "local"))
    ap.add_argument("--llm-mode", default=os.environ.get("LLM_MODE", "fixture"))
    ap.add_argument("--cases", default=None, help="comma-separated case_ids, default all 20")
    ap.add_argument("--no-resume", action="store_true", help="re-run cases that already have an answer file")
    args = ap.parse_args()

    os.environ["GRAPH_BACKEND"] = args.backend
    os.environ["LLM_MODE"] = args.llm_mode

    from agent.graph import run_case
    from backends import get_backend
    from contracts.case_record import validate_case_record

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from validate_answer_file import _load_case_pack_ids, _load_closed_case_ids

    CASES_DIR.mkdir(exist_ok=True)
    rows = load_case_pack()
    if args.cases:
        wanted = set(args.cases.split(","))
        rows = [r for r in rows if r["case_id"] in wanted]

    print(f"loading {args.backend} backend...")
    t0 = time.time()
    backend = get_backend()
    print(f"backend ready in {time.time() - t0:.1f}s")

    known_case_ids = _load_case_pack_ids()
    known_closed_ids = _load_closed_case_ids()

    for row in rows:
        out_path = CASES_DIR / f"{row['case_id']}.json"
        if out_path.exists() and not args.no_resume:
            print(f"[skip] {row['case_id']} already done")
            continue

        print(f"[run]  {row['case_id']} ({row['trigger_type']})...")
        t0 = time.time()
        final_state = run_case(row, backend)
        case_record = final_state["case_record"]
        elapsed = time.time() - t0

        errors = validate_case_record(case_record)
        out_path.write_text(case_record.model_dump_json(indent=2), encoding="utf-8")

        status = "OK" if not errors else f"{len(errors)} FORMAT ISSUES"
        print(f"       verdict={case_record.case.verdict} pattern={case_record.case.pattern} confidence={case_record.case.fraud_probability} [{status}] ({elapsed:.1f}s)")
        for e in errors:
            print(f"         - {e}")


if __name__ == "__main__":
    main()
