"""Case-memory demo for the write-up: run case B against a clean memory (only
closed_cases_history.csv seeded), then run case A (which writes itself into memory),
reset to a fresh clean memory plus A, and run case B again - isolating exactly what
changes for B purely because A is now in the corpus. Two separate memory timelines
(clean+B, clean+A+B) rather than reusing one across both runs, so B never ends up
matching its own earlier write instead of A. Both are real case_pack.csv rows, same
pattern, A opened well before B.

Usage: python scripts/demo_case_memory.py
"""
import csv
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ["GRAPH_BACKEND"] = "local"
os.environ["LLM_MODE"] = "fixture"

CASE_A_ID = "HHG-015"  # opened 2016-11-17, card_not_present_new_device
CASE_B_ID = "DEMO-B"   # synthetic - see note below

# Tried this first with two independent real case_pack rows sharing the same pattern
# label (HHG-015 vs HHG-013): zero similarity even at k=20. Case memory retrieval is
# plain TF-IDF cosine over raw text, not the pattern label, and a freshly-written
# case's stored text (summary + full evidence) is long and topically different from
# the short trigger-based query text used to retrieve it - two cases sharing a pattern
# don't necessarily share vocabulary. That's a real, worth-knowing characteristic of
# this design, not a bug (see the report).
#
# For an illustrative demo that actually shows the retrieval firing, CASE_B below
# reuses case A's own real account/transaction (a "second alert on the same activity"
# scenario, not a fabricated customer) so its query text genuinely overlaps with what
# gets stored for A. This is a deliberately constructed pair to demonstrate the
# mechanism clearly, not a claim that any two same-pattern case_pack rows behave this way.


def load_row(case_id: str) -> dict:
    with (REPO_ROOT / "case_pack.csv").open(encoding="utf-8") as f:
        rows = {r["case_id"]: r for r in csv.DictReader(f)}
    return rows[case_id]


def make_demo_b_row(row_a: dict) -> dict:
    row_b = dict(row_a)
    row_b["case_id"] = CASE_B_ID
    row_b["opened_at"] = "2016-11-18 09:00:00"  # a day after A, same account flagged again
    return row_b


def snapshot(final_state: dict) -> dict:
    cr = final_state["case_record"]
    return {
        "verdict": cr.case.verdict,
        "confidence": cr.case.fraud_probability,
        "final_actions": [a.action for a in cr.next_best_actions.final],
        "top_similar_cases": [
            {"case_id": c["case_id"], "similarity": c["similarity"], "outcome": c["outcome"]}
            for c in sorted(final_state["similar_cases"], key=lambda c: -c["similarity"])[:3]
        ],
    }


def reset_memory_cache():
    for f in ("added_cases.json", "open_cases.json"):
        (REPO_ROOT / "memory" / ".cache" / f).unlink(missing_ok=True)


def main():
    (REPO_ROOT / "ledger.sqlite3").unlink(missing_ok=True)
    reset_memory_cache()

    from agent.graph import run_case
    from backends.local import LocalBackend
    from memory.case_memory import CaseMemory

    backend = LocalBackend()
    row_a = load_row(CASE_A_ID)
    row_b = make_demo_b_row(row_a)

    print(f"=== Timeline 1: run {CASE_B_ID} against a clean memory (no {CASE_A_ID}) ===")
    before_state = run_case(row_b, backend)
    before = snapshot(before_state)
    print(json.dumps(before, indent=2))

    print(f"\n=== Reset to a fresh clean memory, then run {CASE_A_ID} (writes itself in) ===")
    reset_memory_cache()
    backend.memory = CaseMemory()
    a_state = run_case(row_a, backend)
    print(f"{CASE_A_ID}: verdict={a_state['case_record'].case.verdict} pattern={a_state['case_record'].case.pattern} "
          f"confidence={a_state['case_record'].case.fraud_probability} written_to_graph={a_state['case_record'].case.written_to_graph}")

    print(f"\n=== Timeline 2: run {CASE_B_ID} again, now that {CASE_A_ID} is in memory ===")
    after_state = run_case(row_b, backend)
    after = snapshot(after_state)
    print(json.dumps(after, indent=2))

    print(f"\n=== What changed for {CASE_B_ID} because of {CASE_A_ID} ===")
    a_in_before = any(c["case_id"] == CASE_A_ID for c in before["top_similar_cases"])
    a_in_after = any(c["case_id"] == CASE_A_ID for c in after["top_similar_cases"])
    print(f"{CASE_A_ID} in top-3 similar cases before: {a_in_before}")
    print(f"{CASE_A_ID} in top-3 similar cases after:  {a_in_after}")
    if a_in_after:
        entry = next(c for c in after["top_similar_cases"] if c["case_id"] == CASE_A_ID)
        print(f"{CASE_A_ID}'s similarity score to {CASE_B_ID}: {entry['similarity']} (outcome: {entry['outcome']})")
    print(f"confidence: {before['confidence']} -> {after['confidence']}")
    print(f"verdict: {before['verdict']} -> {after['verdict']}")
    print(f"final actions: {before['final_actions']} -> {after['final_actions']}")

    # top-3 is what actually reaches the agent as evidence - also check A's raw rank/score
    # against a wider retrieval so a real-but-modest effect isn't reported as "no effect"
    # just because it didn't crack the top 3 this pair happened to produce
    case_text_b = f"{row_b['trigger_text']} ring size {after_state['ring']['size']} known fraud {after_state['ring']['known_fraud_count']}"
    wide = backend.get_prior_similar_cases(case_text_b, k=20)
    match = next((r for r in wide.results if r.case_id == CASE_A_ID), None)
    if match:
        rank = wide.results.index(match) + 1
        print(f"\n(wider check, k=20) {CASE_A_ID} ranks #{rank} for {CASE_B_ID} at similarity {match.similarity} - "
              f"{'below the top-3 the agent actually sees' if rank > 3 else 'within top-3'}")
    else:
        print(f"\n(wider check, k=20) {CASE_A_ID} does not appear at all in {CASE_B_ID}'s top 20 - "
              "these two cases' wording doesn't overlap enough for TF-IDF to connect them, despite sharing a pattern label")

    out = {"case_a": CASE_A_ID, "case_b": CASE_B_ID, "before": before, "after": after}
    out_path = REPO_ROOT / "scripts" / "demo_case_memory_output.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nsaved to {out_path}")

    reset_memory_cache()
    (REPO_ROOT / "ledger.sqlite3").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
