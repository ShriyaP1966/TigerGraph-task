# HHGOA — TigerGraph Agentic Fraud Investigation

An agentic fraud investigation system built on TigerGraph for the Hacker House Goa hackathon.

## Problem statement

A bank gets uncertain fraud signals every day: a risk-scoring model flags a transaction, a customer disputes a charge, or an analyst asks for a look. Someone (or something) has to investigate each one, decide whether there's enough evidence to act, gather more evidence when there isn't, take a policy-compliant next step, explain the reasoning, and remember the case so the next investigation benefits from it. This project builds an agent that does that against a real fraud dataset (IEEE-CIS transactions, closed cases, and a written fraud policy), producing one structured answer file per case.

## What this system is designed to do

Given a trigger (risk score / customer report / analyst request), the agent:
1. Investigates the transaction graph and prior closed cases
2. Assesses whether it has enough evidence to reach a verdict
3. If not, requests more evidence (customer validation, step-up auth, analyst input) through controlled, simulated channels
4. Recommends or takes next-best actions within an explicit fraud policy (with human approval required for high-impact actions)
5. Explains its reasoning, citing evidence and policy clauses
6. Writes the case back into the graph so future investigations can retrieve it as memory

**Current implementation state**: the dashboard, policy content, and QA tooling described below are built and working. The graph database, the agent itself, and the 20 real investigation answers are **not yet built** — see [Current status](#current-status) for exactly what exists today versus what's designed but pending.

## Key features

| Feature | Status |
|---|---|
| Analyst dashboard (case queue, detail, evidence, confidence, actions, graph view, approvals) | **Implemented**, running against mock case data |
| Real fraud policy & typology content, chunked with stable IDs for graph loading / citation | **Implemented** |
| Answer-file format validator (checks submissions against the dataset's required format) | **Implemented**, tested against 23 deliberately broken cases |
| Case-record JSON contract between agent backend and UI | **Implemented** (schema + example) |
| Proposed approval-action API contract for human-in-the-loop review | **Drafted**, not yet confirmed or implemented by the agent side |
| TigerGraph schema, data loading, GSQL algorithms, MCP tools | **Not yet built** |
| LangGraph agent, confidence engine, policy engine | **Not yet built** |
| Live agent ↔ UI integration | **Not yet built** — UI currently reads a static mock file |
| 20 benchmark case answer files | **Not yet produced** |
| Demo video, blog post, social post | **Not yet produced** |

## Architecture at a glance

```
IEEE-CIS data ─┐
Fraud policy   ─┼─▶ TigerGraph (Savanna/CE) ─▶ tigergraph-mcp ─▶ LangGraph agent ─▶ Streamlit UI
Typologies     ─┤        (graph + vector          (tools)         (Groq/Gemini,        (case queue,
Prior cases    ─┘         storage, GSQL                            confidence           evidence,
                           algorithms)                              engine, policy       approvals,
                                                                     gate, memory)        graph view)
```

Only the rightmost box (Streamlit UI) is built. Everything to its left is designed (see the role briefs below) but not yet implemented. The UI currently reads directly from a mock JSON file in place of the pipeline shown here.

Everything in the stack is intentionally free: TigerGraph Savanna/Community Edition, Groq/Gemini free LLM tiers, local sentence-transformers embeddings, LangGraph, Streamlit — no paid hosting required.

### TigerGraph's intended role

Per the design (not yet implemented): TigerGraph holds the transaction graph (customers, cards, transactions, devices, billing regions), the closed-case history, and a vector index over policy clauses, fraud typologies, and closed-case narratives. GSQL algorithms would compute things like shared-device/region clusters and case similarity. The agent would query it through `tigergraph-mcp` as a set of tools, and write each new investigation back as a case vertex — making "case memory" a graph traversal rather than a separate vector database.

### Agentic investigation workflow (designed, not yet implemented)

The intended flow, as an explicit LangGraph graph: `trigger_intake` → `open_or_load_case` → `gather_graph_evidence` → `gather_graphrag_context` → `assess_patterns_and_risk` → `uncertainty_gate` (loops back to gather more evidence if under-confident) → `decide_actions` → `approval_gate` → `execute_or_record` → `explain` → `update_case_memory`. None of these nodes exist in code yet — this describes the target design from the P2 role brief.

## Person 3 (UI / dashboard) — what's actually built

The Streamlit analyst dashboard (`ui/`) renders case data shaped like `contracts/case_record_schema.json`:

- **Case queue** — sortable table (case ID, trigger, status, risk, confidence, current recommended action), click a row to open it
- **Case detail** — header with status/risk badges, trigger, entities, findings (cross-referenced to evidence), decision log, SAR
- **Evidence timeline** — chronological, typed, each entry traceable to the findings it supports
- **Confidence view** — the agent's confidence score and its named components, rendered as-is (no scoring logic invented in the UI); a sufficiency banner read directly from the case's own status field
- **Recommended actions** — next-best-action before/after any requested evidence, with cited policy clauses resolved to their real text
- **Graph view** — a case-specific subgraph (`streamlit-agraph`), built strictly from the entities the case record actually lists — no fabricated relationships
- **Approval workflow** — a pending-actions queue with Approve/Reject, backed today by a local mock ledger (`ui/lib/mock_actions.py`)

All of this runs against **mock data** (`contracts/case_record_example.json`), by design — it doesn't wait on a live agent. `ui/lib/data.py::load_cases()` is the single point where that gets swapped for real agent output later.

## Policy / typology / GraphRAG document structure

```
docs/policy/
  raw/policy/HHGOA_fraud_policy.md              Real fraud policy, verbatim from the dataset README
  raw/typology/HHGOA_fraud_typologies.md        Real 5 known fraud patterns, verbatim
  raw/regulatory/HHGOA_regulatory_references.md Real content from 5 FinCEN documents (SAR narrative
                                                 guidance, account takeover, money mule/imposter
                                                 scams, filing thresholds, documentation retention),
                                                 fetched and quoted verbatim. Some README1.md-linked
                                                 sources (FFIEC — bot-blocked, FATF, OFAC's SDN list)
                                                 are not chunked; see the file's header comment for why.
  chunks/policy_clauses.json                    POL-001..019, stable IDs, chunked from the above
  chunks/typologies.json                        TYP-001..005
  chunks/regulatory_references.json             REG-001..010
```

Each `##` heading in a raw doc becomes one chunk with a stable ID (cached in `_id_map.json` so re-chunking never renumbers a clause other code already cites). These are what P1 would load as `PolicyClause`/`FraudTypology` graph vertices, and what the UI already resolves policy-clause IDs against (see the Actions & SAR tab).

## Repository structure

```
/contracts        Case-record JSON contract (agent ↔ UI) + a proposed approval-action API contract
/docs/policy       Raw policy/typology/regulatory docs + the chunker output (see above)
/scripts           Standalone tooling: policy chunker, answer-file validator, and their tests
/ui                Streamlit analyst dashboard
  /lib             Data loading, mock approval ledger, styling, graph-view builder
  /components      One module per dashboard section (queue, detail, evidence, confidence, actions, approvals)
  /tests           Dashboard robustness test suite (20 synthetic edge-case records)
/graph             (P1, not yet created) GSQL schema, loading jobs, algorithms
/agent             (P2, not yet created) LangGraph agent, tools, benchmark runner
```

## Technology stack

| Layer | Tool | Status |
|---|---|---|
| UI | Streamlit + streamlit-agraph | **In use** |
| Graph database | TigerGraph Savanna / Community Edition | Not yet connected |
| Graph ↔ agent bridge | tigergraph-mcp | Not yet integrated |
| Agent framework | LangGraph | Not yet built |
| LLM | Groq (primary) / Gemini (backup) | Not yet integrated |
| Embeddings | sentence-transformers, local | Not yet integrated |
| Vector search | TigerGraph native / FAISS fallback | Not yet integrated |

## Prerequisites

- Python 3.11+ (developed against 3.13)
- `pip`
- A modern browser, to view the dashboard
- Nothing else is required to run what's currently implemented — no TigerGraph account, no LLM API key, no `.env` file. Those will become necessary once the agent (P2) and graph (P1) pieces are built.

## Installation & setup

```bash
git clone https://github.com/ShriyaP1966/T1-TigerGraph.git
cd T1-TigerGraph/ui
pip install -r requirements.txt
```

## Environment variables

**None are required today.** The current codebase (dashboard, chunker, validator) makes no external API calls and reads only local files. Once the agent is built, expect `GROQ_API_KEY`, `GOOGLE_API_KEY` (Gemini), and a TigerGraph connection string/token to be needed — none of that exists in this repo yet, and no `.env` file or secret is committed here.

## Running the application

```bash
cd ui
streamlit run app.py
```

Opens at `http://localhost:8501`. Renders the mock cases in `contracts/case_record_example.json` — this is the full dashboard experience today, since there's no live agent to connect to yet.

## How mock data works

`ui/lib/data.py::load_cases()` reads `contracts/case_record_example.json`, a small set of case records matching `contracts/case_record_schema.json` exactly. Approvals made in the UI are recorded in a local JSON ledger (`ui/.local/audit_ledger.json`, gitignored, created on first use) and overlaid onto the loaded cases at read time — the original mock file is never modified. This keeps the whole dashboard fully functional and testable without any backend.

## How the UI connects to the case-record schema

`contracts/case_record_schema.json` is the contract: every field the dashboard renders (trigger, entities, evidence, findings, risk assessment, decisions, SAR, next-best-action, case memory) is defined there first. Every UI component reads only fields defined in that schema — nothing is invented or assumed beyond it, so a real agent producing schema-valid output should render correctly without UI changes.

## Live agent integration (P2) — planned, not yet implemented

Two swap points are already isolated for this, so connecting a real agent shouldn't require touching any rendering code:

- **Case data**: replace the body of `ui/lib/data.py::load_cases()` to read the agent's live output instead of the mock file.
- **Approvals**: replace `ui/lib/mock_actions.py::record_decision()` to call a real approval/execution API instead of writing to the local ledger. A proposed contract for that API is drafted at `contracts/approval_action_api_schema.json` (request/response shapes, mirroring the case schema's `decisions_and_actions[]` fields) — **proposed only, awaiting confirmation from whoever builds the agent side.**

## Testing / QA

```bash
python ui/tests/test_dashboard_robustness.py       # dashboard vs. 20 synthetic edge-case records
python scripts/tests/test_validate_answer_file.py  # answer-file validator vs. a valid + a broken fixture
```

- `ui/tests/` renders every dashboard component against 20 synthetic case records probing edge cases a live agent is likely to produce: empty collections, null/out-of-vocabulary enum values, boundary confidence scores, very long or HTML-breaking text, large entity counts, and more. All pass.
- `scripts/tests/` proves the answer-file validator (below) against the dataset README's own worked example (must pass clean) and a fixture with 23 deliberately planted violations (must catch all of them). Both confirmed.

Neither suite requires network access, a browser, or a running server — both are plain Python scripts using `streamlit.testing.v1.AppTest` under the hood.

## Benchmark cases

`case_pack.csv` lists the 20 real benchmark cases (case ID, trigger, flagged transaction, card, customer). `closed_cases_history.csv` is the labeled history (5,565 closed investigations) the agent is meant to use as memory. `README1.md` is the full dataset README: task description, column definitions, the five known fraud patterns, the fraud policy (with numbered rules R1–R10), and the exact required answer-file format. **No answer files exist yet** — they're produced by the agent, which isn't built.

## Validating an answer file (Phase 4 tooling)

```bash
python scripts/validate_answer_file.py cases/HHG-001.json   # one file
python scripts/validate_answer_file.py cases/                # whole folder
```

Checks a case answer file against the dataset README's exact Answer Format — required fields, enums, and cross-field rules (legitimate verdicts must have empty `affected_txn_ids`/zero `exposure_usd`; `sar.file` must match whether `FILE_REPORT` appears in the final actions; approval routes must match the policy's routing table, including the exposure-dependent `BLOCK_CARD` rule). Also flags any `case_id` or `similar_prior_cases` entry not found in `case_pack.csv` / `closed_cases_history.csv`. **This checks format and internal consistency, not investigative correctness.**

## Running the policy chunker

```bash
python scripts/chunk_policy_docs.py
```

Reads `docs/policy/raw/{policy,typology,regulatory}/*.md`, writes `docs/policy/chunks/{policy_clauses,typologies,regulatory_references}.json` with stable IDs. Safe to re-run — IDs are cached in `docs/policy/chunks/_id_map.json` and won't shift when a doc is edited or a new one is added.

## Demo

Not yet produced. Planned per the submission requirements: a 3–5 minute video showing trigger → evidence gathering → uncertainty → requesting more evidence → action → explanation, plus a second case demonstrating memory reuse. This requires a working end-to-end agent, which doesn't exist yet.

## Current status

- [x] **Phase 0 — Align & set up.** Case-record JSON contract defined and validated, Streamlit skeleton scaffolded and running.
- [x] **Phase 1 — Policy doc prep.** Real fraud policy (`POL-001`–`019`), typologies (`TYP-001`–`005`), and regulatory references (`REG-001`–`010`, from 5 FinCEN documents) all chunked with real content — no placeholders remain anywhere in `docs/policy/chunks/`.
- [x] **Phase 2 — Streamlit dashboard (core).** All views listed above, built against mock data and manually verified in-browser. Not done: live wiring, conversational panel, public deployment (the last two are explicitly out of scope for now).
- [ ] **Phase 3 — Live integration with the real agent.** Blocked on the agent and graph existing. Prep done: HTML-escaping hardening (so LLM-generated text with `<`/`>`/`&` can't break the UI), a 20-case synthetic stress test, and a proposed approval-API contract awaiting confirmation.
- [ ] **Phase 4 — QA of all 20 benchmark answer files.** Blocked on those files existing. Prep done: the answer-file validator above, proven against the README's own example and 23 planted violations.
- [ ] **Phase 5 — Demo video, blog post, social post.** Not started — depends on a working end-to-end system.

## Known limitations

- No TigerGraph instance, schema, or loaded data yet — none of the graph-side claims in the architecture diagram are live
- No agent — the "agentic workflow" above is a design, not running code
- `transactions.csv` (the ~708MB core transaction table) is not yet in this repo
- Regulatory references cover 5 of the ~15 sources README1.md links (FFIEC pages are bot-blocked from this environment; FATF's 6 reports and OFAC's SDN list were deprioritized as lower-relevance to card-fraud red flags specifically — see the raw file's header for details)
- Mock data covers only 2 illustrative cases; dashboard behavior at the real scale (20+ cases with agent-generated text) is stress-tested with synthetic data, not real agent output
- No `.env`/secrets infrastructure exists yet since nothing currently needs one

## Future improvements

1. P1: TigerGraph schema, data loading, GSQL algorithms, MCP tools
2. P2: LangGraph agent, confidence/policy engine, confirm or amend the proposed approval-action API contract
3. P3: swap `load_cases()`/`mock_actions.py` to the real agent once it exists, then QA all 20 answer files with the validator, then demo/blog/social

## License

No license file is currently included in this repository.

## Submission requirements (tracking)

- [ ] Working agent (code in this repo)
- [ ] GitHub repository, shared with judges
- [ ] One answer file per benchmark case (20 total): case record, evidence, findings, decisions, actions taken
- [ ] Each case also written into the graph
- [ ] Suspicious Activity Report generated when policy requires it
- [ ] Next-best action + approval route recorded both before and after any additional evidence is gathered
- [ ] 3–5 minute demo video
- [ ] Technical blog post (what we built, architecture, how TigerGraph is used, agentic capabilities, what we learned, what we'd improve)
- [ ] Social post on X or LinkedIn tagging @TigerGraphDB

Submit at: https://forms.gle/yxXzqSULGgZ9VUF56 — one submission per team, by the team lead, by **Sept 24, 2026, 11:59 PM IST**. No resubmissions.

Support: TigerGraph Discord https://discord.gg/7JMkCAy9D3
