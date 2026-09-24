# Person 3 Progress — UI, GraphRAG Docs & Demo Lead

## Phase 1 — Policy doc prep (complete, including regulatory references)

Real HHGOA_IEEE fraud policy and typologies extracted verbatim from
`README1.md` into `docs/policy/raw/policy/HHGOA_fraud_policy.md` and
`docs/policy/raw/typology/HHGOA_fraud_typologies.md`. Regulatory references
fetched separately from README1.md's linked FinCEN/FATF/FFIEC/OFAC sources
(see below) into `docs/policy/raw/regulatory/HHGOA_regulatory_references.md`.
All SAMPLE placeholders removed. Chunker re-run with a reset ID map:

- `POL-001`–`POL-019` — real policy (sections 0–7, rules R1–R10)
- `TYP-001`–`TYP-005` — real typologies (the 5 known fraud patterns)
- `REG-001`–`REG-010` — real regulatory content, no placeholders remain

### Regulatory references — how they were fetched

`WebFetch` on a PDF URL returns raw binary/compressed content that its
AI-summarization step can't read (it only converts HTML → markdown). The
working pattern: `WebFetch` still downloads and saves the PDF locally even
when it reports it can't parse it — the save path is in its response — then
`Read` on that saved path extracts the real text (Read has native PDF
support). HTML pages (e.g. FinCEN's advisory pages) fetch and summarize
fine directly via `WebFetch`. This is the pattern to reuse for any future
PDF-based source.

Fetched and chunked (5 of ~15 README1.md-linked sources, all real, quoted
verbatim or near-verbatim with source attribution):
1. FinCEN, "Guidance on Preparing A Complete & Sufficient SAR Narrative" (Nov 2003) → `REG-001`, `REG-002`
2. FinCEN Advisory FIN-2011-A016, "Account Takeover Activity" → `REG-003`, `REG-004`
3. FinCEN Advisory FIN-2020-A003, "Imposter Scams and Money Mule Schemes" → `REG-005`, `REG-006`, `REG-007`
4. FinCEN/Fed/FDIC/NCUA/OCC, "SAR FAQs" (Oct 2025) → `REG-008`, `REG-009`
5. FinCEN Guidance FIN-2007-G003, "SAR Supporting Documentation" → `REG-010`

Not fetched, and why (documented in the raw file's own header comment, not
hidden):
- **FFIEC** (`bsaaml.ffiec.gov/manual/...`, 2 links) — returned HTTP 403 (bot-blocked) from this environment on both attempts. Genuinely inaccessible here, not skipped by choice.
- **FinCEN** "SAR Activity Review" and "Identity-Related Suspicious Activity, 2021" (2 links) — deprioritized once the 5 fetched documents already gave strong, directly relevant coverage.
- **FATF** (6 linked reports) — deprioritized: these cover cross-border money-laundering methodology (trade-based laundering, correspondent banking, remittance networks), which is less directly relevant to this project's card-transaction fraud scope than the FinCEN material already covered.
- **OFAC** SDN list (1 link) — a raw sanctioned-entity list, not prose guidance; not meaningful to chunk the same way. Its purpose is already referenced in `REG-001`'s discussion of what a SAR introduction should note.

Picking this up later to fetch the remaining sources: follow the same
WebFetch → (PDF: Read the saved path) pattern, add `##`-headed chunks to
`docs/policy/raw/regulatory/HHGOA_regulatory_references.md`, then re-run
`scripts/chunk_policy_docs.py`.

## Phase 2 — Streamlit analyst dashboard (core complete)

Built against `contracts/case_record_schema.json` /
`case_record_example.json` only. No fields invented beyond the schema. Does
not wait on P2's live agent — `lib/data.py` is the single swap point for
that later.

### Files changed

| File | What it does |
|---|---|
| `ui/app.py` | Rewritten. Page config, sidebar nav (Case Queue / Case Detail / Approvals), wires all components together. |
| `ui/lib/data.py` | Loads cases from `contracts/case_record_example.json`, policy/typology chunks from `docs/policy/chunks/`. Single point to swap in P2's live output later. |
| `ui/lib/mock_actions.py` | Mock action API / audit ledger for approvals. `record_decision()` is the only function that mutates decision status; `apply_overlay()` merges recorded decisions onto loaded cases at read time without touching the mock file. Ledger persists at `ui/.local/audit_ledger.json` (gitignored). |
| `ui/lib/styling.py` | Validated status palette (good/warning/serious/critical), sequential blue ramp for magnitude bars, badge helpers (color always paired with icon + label), shared CSS. |
| `ui/lib/graph_view.py` | Builds a case-specific subgraph (streamlit-agraph) strictly from `entities`, `fraud_pattern_identified`, and `case_memory.similar_prior_cases_used` — no fabricated edges (e.g. transactions link to the case, not to a guessed account, since the schema doesn't say which account owns which transaction). |
| `ui/components/queue.py` | Case queue: sortable/selectable table (case ID, trigger, status, risk, confidence progress bar, current recommended action, updated-at). Row click drives navigation. |
| `ui/components/detail.py` | Case header (status/risk badges), trigger + entities, findings (with evidence back-references), decision log, SAR, case memory, explanation. |
| `ui/components/evidence.py` | Chronological evidence timeline; each entry shows evidence_id, type, description, source_tool, timestamp, and which findings it supports. |
| `ui/components/confidence.py` | Confidence score + risk badge, confidence_breakdown as bars on the sequential ramp, rationale. "Sufficient evidence" banner is read off the case's existing `status` field — no invented threshold/formula. |
| `ui/components/actions.py` | next_best_action before/after evidence, computed "changed / unchanged" note, evidence requests, SAR policy_clause_ids resolved against real `POL-*` chunk text in expanders. |
| `ui/components/approvals.py` | Global pending-approvals queue across all cases (`requires_approval` + status recommended/pending_approval). Approve/Reject buttons call `lib.mock_actions.record_decision()`. |
| `.gitignore` | Added `ui/.local/` (runtime mock ledger). |

### Features completed

1. **Case queue** — table view, case ID/trigger/risk/confidence/status/recommended action, click-to-select.
2. **Case detail** — header, trigger, entities, findings, decision log, SAR.
3. **Evidence timeline** — chronological, typed, traceable to findings.
4. **Confidence/uncertainty view** — score, per-component bars (schema's own `confidence_breakdown`), status-driven sufficiency banner.
5. **Recommended actions** — before/after NBA, approval-route badges, cited policy clauses with real clause text on expand.
6. **Graph visualization** — case-specific subgraph via streamlit-agraph, grounded only in schema fields.
7. **Approval workflow** — pending queue, Approve/Reject, mock ledger, clean swap point for P2's real API.
8. **UI quality** — consistent badge/color system (validated palette, color+icon+label, never color-alone), card layout, tabbed detail view.

Explicitly **not** done yet (per this task's scope): `transactions.csv` not touched, regulatory references not chunked, no conversational chat panel, no public deployment.

### Tests performed

- `streamlit.testing.v1.AppTest` smoke runs (no browser needed) covering:
  - Case Queue renders, 0 exceptions.
  - Case Detail for both mock cases (`CASE-000001`, `CASE-000002`), all 5 tabs, 0 exceptions.
  - Approvals page renders, correctly finds the one pending decision (`CASE-000001` / `D1`).
  - Clicking **Approve** on that decision → ledger written, button disappears from the pending list on rerun.
  - Reloading Case Detail for `CASE-000001` afterward → decision log shows **Approved**, confirming the mock-ledger overlay round-trips correctly.
- Real `streamlit run app.py --server.headless true` boot check: HTTP 200 on `/` and `/_stcore/health`, no tracebacks in server log (catches issues AppTest's bare-mode runner could mask, e.g. the `streamlit-agraph` custom component).
- Verified no stray runtime state left behind after tests (`ui/.local/` cleaned).

### Known issues / limitations

- Case queue row-click selection depends on `st.dataframe(..., on_select="rerun")`, which requires Streamlit ≥1.35 (installed: 1.64 — fine, but pin worth adding to `requirements.txt` if this becomes a submission concern).
- Graph view's edges are intentionally sparse where the schema is silent (e.g. transaction→account ownership isn't in `entities`) — this is correct per the "don't fabricate" instruction, but means the graph looks flatter than the full TigerGraph model once P1's real graph is wired in.
- Only 2 mock cases in `contracts/case_record_example.json`, so the real demo data itself is still thin (the 20-case stress test below covers rendering robustness, not demo content).

### Bug found and fixed during manual QA

**Symptom** (caught by the user clicking a queue row in a real browser, not by automated tests): `StreamlitWidgetAlreadyInstantiatedError: st.session_state.nav cannot be modified after the widget with key nav is instantiated.`

**Cause**: `ui/app.py` wrote to `st.session_state.nav` (to jump from Case Queue to Case Detail) *after* the sidebar's `st.radio(..., key="nav")` had already rendered earlier in that same script run — Streamlit forbids that.

**Fix**: introduced a `nav_override` session-state key, applied *before* the radio widget is created on the next run, instead of writing to `nav` directly mid-run.

**Process gap this exposed**: the original `AppTest` smoke suite set `session_state["nav"]` directly before `.run()` to test each destination screen, which never actually exercised the click-triggered transition. Added a follow-up test that simulates the real dataframe row-selection event (`at.session_state["case_queue_table"] = {"selection": {"rows": [0], ...}}`) and asserts the full Queue→Detail transition — this is now the regression test for this exact bug class.

### Manual verification (real browser, by the user)

All of Phase 2's required views were checked live at `http://localhost:8501` against both mock cases, including the one component automated tests can't fully exercise: the Graph tab (streamlit-agraph renders client-side JS/vis.js — confirmed the case-centered subgraph actually renders and settles correctly for both cases). Also manually verified the Approve button round-trip (click → ledger write → reflected back in the decision log).

## Phase 3 prep — the parts that don't depend on P1 or P2

Phase 3 itself ("live integration with the real agent") is blocked: P1 hasn't loaded a graph, P2 hasn't built the agent, so there's no live output to wire the dashboard to yet. Three things *don't* have that dependency and are done:

### 1. HTML-escaping hardening (real bug, found via stress-testing)

All case-derived free text (trigger details, findings, decision rationale, SAR content, explanation, evidence descriptions, confidence rationale, evidence-request reason/result) was being interpolated directly into `unsafe_allow_html` blocks with no escaping. Harmless today because the 2 mock cases contain clean text, but once P2's agent generates this text via an LLM, a rationale like `"score < 0.70"` or `"exposure > $500"` would be parsed as a stray HTML tag and visibly break the layout.

**Fix**: added `lib/styling.py::esc()` (thin wrapper on `html.escape`) and applied it at every dynamic-text interpolation point across `components/detail.py`, `evidence.py`, `confidence.py`, `actions.py`, and `approvals.py`. Also centralized it inside `styling.py::badge()` so every badge helper gets it for free on out-of-vocabulary fallback labels. Streamlit's own `st.dataframe` (queue table) and `st.write`/`st.expander` (policy clause text) don't go through `unsafe_allow_html`, so they needed no change; `streamlit-agraph` node labels are canvas-drawn by vis.js, not HTML, so also unaffected.

### 2. 20-case synthetic stress-test suite (`ui/tests/`)

- `ui/tests/fixtures.py` — 20 synthetic case records, all valid against `case_record_schema.json`, each probing a different edge Phase 3's real (LLM-backed) data is likely to hit: empty collections, null/out-of-vocabulary enum values, confidence-score boundaries (0.0/1.0), empty entities (graph empty-state), 30 transactions (scale), unknown policy clause IDs, very long text, **HTML/markup-breaking characters** (the regression test for the fix above), unicode/emoji, missing optional fields, unchanged vs. escalated next-best-action, 12 similar prior cases (scale), and a case with mixed already-resolved decision statuses (approvals-queue filtering).
- `ui/tests/_stress_app.py` — standalone Streamlit script (not `app.py`) that renders *every* component (not just one tab) against a chosen synthetic case, selected via `session_state["case_idx"]`. Kept separate so stress-testing never touches the real app or its data source.
- `ui/tests/test_dashboard_robustness.py` — drives `AppTest` across all 20 cases and asserts zero exceptions. Runnable standalone (`python ui/tests/test_dashboard_robustness.py`, no pytest dependency added) or under pytest later.
- **Result: all 20/20 pass**, including the HTML-injection case — confirms the escaping fix works.

### 3. Proposed approval-action API contract (`contracts/`)

P2 has published the case-record schema, but nothing yet defines what the real approval/execute endpoint should look like — the UI currently only has a local mock (`ui/lib/mock_actions.py`). Drafted a proposed contract for P2 to review, in the same style as `case_record_schema.json`:

- `contracts/approval_action_api_schema.json` — `POST /cases/{case_id}/decisions/{decision_id}/review`, request (`status`, `actor`, optional `note`) and response shapes, deliberately mirroring `decisions_and_actions[]` fields so wiring the real thing later only means changing `mock_actions.record_decision()`'s body. Flags one design gap explicitly: the mock doesn't currently prevent two analysts racing to resolve the same decision; the real endpoint should return a 409-style error instead of silently overwriting.
- `contracts/approval_action_api_example.json` — example approve/reject/error payloads.
- **Status: proposed only, not confirmed by P2.** Not wired into the UI — `ui/lib/mock_actions.py` is unchanged and still the active implementation.

### Exact next recommended task (as of end of Phase 3 prep)

Still genuinely blocked on Phase 3 proper. Best next steps, in order:
1. Get P2 to confirm/amend `contracts/approval_action_api_schema.json` (5-minute read, unblocks a clean Phase 3 swap later).
2. Everything else queued from before: the queue-row "N pending" indicator (discussed, not yet built), regulatory references chunking, or Phase 4/5 prep.

## Phase 4 prep — the parts that don't depend on P1 or P2

Phase 4 itself ("QA of all 20 benchmark answer files against the dataset README") is blocked the same way Phase 3 is: the `cases/<case_id>.json` answer files only exist once P1's graph + P2's agent actually run all 20 investigations. **Important distinction surfaced here**: the Phase 4 target format is README1.md's **Answer Format** section, not `contracts/case_record_schema.json` — those are two different JSON shapes (the schema is the internal P2↔P3 UI contract; the Answer Format is the actual submission format graders see). Someone — likely P2 — needs a conversion step between them; flagging this now so it isn't discovered late.

What doesn't depend on P1/P2: the QA tool itself, built and proven against real dataset files.

### `scripts/validate_answer_file.py`

Checks a `cases/<case_id>.json` file (or a whole folder) against README1.md's Answer Format field-by-field — required fields, enum values (`status`, `verdict`, `pattern`, evidence `source`, evidence-request `type`, action names, routes), and every cross-field rule the spec states explicitly:

- `verdict == "legitimate"` ⇒ `affected_txn_ids == []` and `exposure_usd == 0`
- `pattern == "undocumented"` ⇒ `pattern_description` required non-empty, else must be `""`
- `sar.file` must agree with whether `FILE_REPORT` appears in `next_best_actions.final`
- `sar.file == true` ⇒ `narrative`/`subjects`/`activity_dates` required; `sar.file == false` ⇒ all cleared to empty/zero
- **Approval-route policy check** (Fraud Policy §2, cross-referenced against `case.exposure_usd`): auto-only actions must route `auto`, `DECLINE_TRANSACTION` must be `L1`, `BLOCK_ALL_CARDS`/`FILE_REPORT` must be `L2`, `BLOCK_CARD` must be `L1` at/under $2,500 exposure and `L2` above it
- Cross-checks `case_id` against the real `case_pack.csv` (20 valid IDs) and every `similar_prior_cases` entry against the real `closed_cases_history.csv` — catches a made-up ID before submission, per README1.md: *"Made-up IDs score zero."*

This checks **format and internal consistency**, not investigative correctness — it can't tell you the verdict is right, only that the file is shaped the way grading expects and doesn't contradict itself.

Usage: `python scripts/validate_answer_file.py cases/HHG-001.json` or point it at the whole `cases/` folder.

### Proof it works (`scripts/tests/`)

- `fixtures/valid_answer_example.json` — README1.md's own worked example (`HHG-017`) copied verbatim. **Validates clean**, including the real cross-checks (confirmed `HHG-017` is a real case in `case_pack.csv` and `CC-0141` a real row in `closed_cases_history.csv` before relying on them).
- `fixtures/invalid_answer_example.json` — one file with 23 deliberately planted violations (bad case_id, wrong verdict/exposure combination, invalid enums, SAR/FILE_REPORT mismatch, wrong approval routes for `BLOCK_ALL_CARDS` and a high-exposure `BLOCK_CARD`, made-up prior-case ID, missing required fields, wrong types).
- `test_validate_answer_file.py` — runs the validator against both fixtures and asserts each of the 23 expected violations fired with the right message. **All 23/23 confirmed.**

### Exact next recommended task

1. Ask P2 who owns the conversion from `case_record_schema.json` → the Answer Format this validator checks (the gap flagged above) — better to settle this before 20 real cases need converting under deadline pressure.
2. Once real answer files start appearing in `cases/`, run this validator on each one immediately, not saved up for a final QA pass — catches format drift early per-case instead of in bulk at the end.
3. Otherwise, same queue as before: Phase 3's approval-API contract awaiting P2's confirmation, the queue-row pending indicator, regulatory references, or Phase 5 prep (demo storyboard, blog outline).
