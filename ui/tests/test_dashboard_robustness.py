"""Renders all 20 synthetic stress cases (fixtures.py) through every
dashboard component and asserts none of them raise an exception.

Run directly:  python ui/tests/test_dashboard_robustness.py
Or under pytest, once it's added to the project: pytest ui/tests/

This exists to catch what happened once already during manual testing (a
StreamlitWidgetAlreadyInstantiatedError from a real click path AppTest
hadn't exercised) and to catch what Phase 3's live, LLM-generated case data
will do to this UI before it actually does it — see fixtures.py for what
each case is probing (empty collections, null/out-of-vocabulary enums,
boundary scores, HTML-breaking text, large entity counts, ...).
"""

from __future__ import annotations

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import build_stress_cases  # noqa: E402

STRESS_APP = str(Path(__file__).resolve().parent / "_stress_app.py")
TIMEOUT = 90


def test_all_stress_cases_render_without_exception() -> None:
    cases = build_stress_cases()
    failures: list[str] = []

    for i, case in enumerate(cases):
        at = AppTest.from_file(STRESS_APP)
        at.session_state["case_idx"] = i
        at.run(timeout=TIMEOUT)
        if len(at.exception):
            failures.append(
                f"[{i}] {case.get('case_id')}: " + "; ".join(str(e) for e in at.exception)
            )

    assert not failures, (
        f"{len(failures)}/{len(cases)} synthetic case(s) raised an exception:\n"
        + "\n".join(failures)
    )


def _run_as_script() -> None:
    cases = build_stress_cases()
    print(f"Rendering {len(cases)} synthetic stress cases through every dashboard component...\n")
    failures = []
    for i, case in enumerate(cases):
        at = AppTest.from_file(STRESS_APP)
        at.session_state["case_idx"] = i
        at.run(timeout=TIMEOUT)
        ok = len(at.exception) == 0
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {case['case_id']}")
        if not ok:
            for e in at.exception:
                print(f"         {e}")
            failures.append(case["case_id"])

    print()
    if failures:
        print(f"{len(failures)}/{len(cases)} FAILED: {failures}")
        sys.exit(1)
    else:
        print(f"All {len(cases)} synthetic cases rendered cleanly.")


if __name__ == "__main__":
    _run_as_script()
