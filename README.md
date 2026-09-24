# HHGOA — TigerGraph Agentic Fraud Investigation

An agentic fraud investigation system built on TigerGraph for the Hacker House Goa hackathon.

## Problem statement

A bank gets uncertain fraud signals every day: a risk-scoring model flags a transaction, a customer disputes a charge, or an analyst asks for a look. Someone (or something) has to investigate each one, decide whether there's enough evidence to act, gather more evidence when there isn't, take a policy-compliant next step, explain the reasoning, and remember the case so the next investigation benefits from it. This project builds an agent that does that against a real fraud dataset (IEEE-CIS transactions, closed cases, and a written fraud policy), producing one structured answer file per case.

## What this system does

Given a trigger (risk score / customer report / analyst request), the agent:
1. Investigates the transaction graph and prior closed cases
2. Assesses whether it has enough evidence to reach a verdict
3. If not, requests more evidence (customer validation, step-up auth, analyst input) through controlled, simulated channels
4. Recommends or takes next-best actions within an explicit fraud policy (with human approval required for high-impact actions)
5. Explains its reasoning, citing evidence and policy clauses
6. Writes the case back into the graph so future investigations can retrieve it as memory

**Current implementation state**: end to end and working — TigerGraph schema/loading/algorithms, the LangGraph agent, the analyst dashboard, and all 20 benchmark answer files are built. See [Current status](#current-status) for the exact phase-by-phase breakdown.

## Key features

| Feature | Status |
|---|---|
| TigerGraph schema, loading jobs, derived fraud-ring edges, GSQL investigation queries, case write-back | **Implemented** (`graph/`) |
| MCP tool layer (`tigergraph-mcp`-shaped), fixture + live modes | **Implemented** (`mcp/`, `graph/mcp/`) |
| LangGraph agent — trigger → evidence → confidence → uncertainty gate → actions → approval → explain → memory write | **Implemented** (`agent/`) |
| Confidence engine (named, weighted components) + policy gate (auto/L1/L2 routing) | **Implemented** (`scoring/`, `policy/`) |
| Case memory (`SIMILAR_TO`-style retrieval, graph-native) | **Implemented** (`memory/`), demonstrated in `scripts/demo_case_memory_output.json` |
| Analyst dashboard (case queue, detail, evidence, confidence, actions, graph view, approvals) | **Implemented**, now reading live agent output |
| Real fraud policy & typology content, chunked with stable IDs for graph loading / citation | **Implemented** |
| Answer-file format validator | **Implemented**, tested against 23 deliberately broken cases |
| Live agent ↔ UI integration | **Implemented** — `ui/lib/data.py` reads real cases via `api.py`; approvals write to the real sqlite policy ledger |
| 20 benchmark case answer files | **Implemented and validated** — all 20 pass `scripts/validate_answer_file.py` |
| Demo video, blog post, social post | See `DEMO_VIDEO_SCRIPT.md`, `BLOG_POST.md`, `SOCIAL_POST.md` |

## Architecture at a glance

```
IEEE-CIS data ─┐
Fraud policy   ─┼─▶ TigerGraph (Savanna/CE) ─▶ mcp/tools.py ─▶ LangGraph agent ─▶ api.py ─▶ Streamlit UI
Typologies     ─┤        (graph + derived        (7 tools,       (agent/graph.py:     (stable       (case queue,
Prior cases    ─┘         fraud-ring edges,        fixture/live)   trigger_intake →    interface)    evidence,
                           GSQL algorithms)                        ... → update_                     approvals,
                                                                    case_memory)                      graph view)
```

Everything left of `api.py` is P1 (graph) + P2 (agent); `api.py` is the frozen interface between them and the UI (P3). `ui/lib/data.py::load_cases()` reads the 20 real answer files in `cases/` through it, falling back to a small mock contract file only if `cases/` is ever empty.

Everything in the stack is intentionally free: TigerGraph Savanna/Community Edition, Groq/Gemini free LLM tiers (with an offline `fixture` LLM mode and a `local` graph backend for zero-dependency runs), LangGraph, Streamlit — no paid hosting required.

### TigerGraph's role

TigerGraph (`graph/schema/01_schema.gsql`) holds `Customer`, `Card`, `Transaction`, `DeviceProfile`, `EmailDomain`, `BillingRegion` vertices from the IEEE-CIS data, plus `ClosedCase` (immutable prior-case history) and `InvestigationCase` (this agent's own cases) as case memory. `graph/algorithms/03_derived_edges.gsql` builds the fraud-ring backbone (`SHARES_DEVICE`/`SHARES_EMAIL`/`SHARES_ADDRESS` between cards), and `04_graph_queries.gsql` exposes six investigation queries (account subgraph, fraud-ring detection via weakly-connected-components, transaction velocity, prior similar cases, policy context, shortest path). `05_case_writeback.gsql` writes each finished investigation back as a case vertex — making "case memory" a graph traversal, not a bolted-on vector DB. The agent reaches all of this through `mcp/tools.py`, a 7-tool contract matching `contracts/mcp_tool_contracts.json`, switchable between `fixture` (canned, contract-shaped data, no connection needed) and `live` (real TigerGraph via `pyTigerGraph`) via `MCP_MODE`.

**Live-instance validation status** (as of the last graph update): the schema and loading jobs compile clean and dimension tables load with 0 errors against a real TigerGraph CE 4.2.5 instance; the full transaction load didn't finish (Docker host ran out of RAM), and `03_derived_edges.gsql`/`05_case_writeback.gsql` are written but not yet run against that live instance (`05` has one known bug — an undefined reverse-edge reference — flagged for the next fix). The 20 answer files in `cases/` and the dashboard both currently run against `GRAPH_BACKEND=local` (`backends/local.py`), a pandas + NetworkX reimplementation of the identical queries over the same real IEEE-CIS-derived data — algorithmically the same graph logic, just not executed inside TigerGraph itself for this submission. See `graph/README.md` for the exact validation notes.

### Agentic investigation workflow

Implemented as an explicit LangGraph graph in `agent/graph.py`: `trigger_intake` → `open_or_load_case` → `gather_graph_evidence` → `gather_graphrag_context` → `assess_patterns_and_risk` → `uncertainty_gate` (loops back to request more evidence — step-up auth, customer validation, analyst input — if under-confident) → `decide_actions` → `approval_gate` → `execute_or_record` → `explain` → `update_case_memory`. `run_benchmark.py` runs this over all 20 `case_pack.csv` rows and writes one answer file per case to `cases/`.

## Person 3 (UI / dashboard) — what's built

The Streamlit analyst dashboard (`ui/`) renders case data shaped like `contracts/case_record_schema.json`:

- **Case queue** — sortable table (case ID, trigger, status, risk, confidence, current recommended action), click a row to open it
- **Case detail** — header with status/risk badges, trigger, entities, findings (cross-referenced to evidence), decision log, SAR
- **Evidence timeline** — chronological, typed, each entry traceable to the findings it supports
- **Confidence view** — the agent's confidence score, rendered as-is (no scoring logic invented in the UI); a sufficiency banner read directly from the case's own status field
- **Recommended actions** — next-best-action before/after any requested evidence, with cited policy clauses resolved to their real text
- **Graph view** — a case-specific subgraph (`streamlit-agraph`), built strictly from the entities the case record actually lists — no fabricated relationships
- **Approval workflow** — a pending-actions queue with Approve/Reject, backed by the real sqlite policy ledger (`actions/ledger.py`, same one the agent itself writes to) via `api.approve()`, with a live pending-count badge in the sidebar nav

`ui/lib/data.py::load_cases()` reads the 20 real answer files in `cases/` via `api.get_case()` (which also seeds the policy ledger for a case on first load, so the approvals queue and decision log are live, not simulated). It falls back to `contracts/case_record_example.json` only if no answer files exist yet, so the dashboard still runs standalone in a clean checkout before `run_benchmark.py` has been run.

**Known, documented gap**: `confidence_breakdown` (the per-component score bars) is only populated for cases run through the live `api.run_case()` path in the same process — it's ephemeral agent state, not part of the graded Answer Format, so reloading a case from `cases/*.json` alone can't recover it. Everything else the Answer Format does carry (evidence, findings, connected cards/devices, next-best-actions, decisions) is fully wired.

## Policy / typology / GraphRAG document structure

```
docs/policy/
  chunks/policy_clauses.json           POL-001..019, stable IDs
  chunks/typologies.json               TYP-001..005
  chunks/regulatory_references.json    REG-001..010, from 5 FinCEN documents (SAR narrative
                                        guidance, account takeover, money mule/imposter scams,
                                        filing thresholds, documentation retention). Some
                                        README1.md-linked sources (FFIEC — bot-blocked, FATF,
                                        OFAC's SDN list) were deliberately not chunked — see
                                        docs/policy/raw/README.md for why.
```

Each `##` heading in a raw source doc became one chunk with a stable ID (cached in `docs/policy/chunks/_id_map.json` so re-chunking never renumbers a clause other code already cites). P1 loads these as `PolicyClause`/`FraudTypology` graph vertices; the UI resolves policy-clause IDs against this same content in the Actions & SAR tab.

## Repository structure

```
/agent             LangGraph agent (graph.py, nodes.py, patterns.py, rules.py, state.py)
/graph             TigerGraph schema, loading jobs, GSQL algorithms, case write-back (P1)
/mcp               MCP tool layer backing the 7-tool contract (fixture/live)
/backends          GraphBackend implementations: mock, local, tigergraph
/llm               LLM client (Groq/Gemini/fixture modes)
/scoring           Confidence engine
/policy            Policy table + approval gate (auto/L1/L2 routing)
/actions           sqlite action ledger
/memory            Case-memory cache/retrieval
/contracts         Case-record JSON contract (agent ↔ UI), Answer Format models, ui_adapter.py
                    (bridges the two), approval-action API contract
/docs/policy       Chunked policy/typology/regulatory content (see above)
/scripts           Policy chunker, answer-file validator, benchmark/memory demo scripts + tests
/cases             The 20 graded answer files (HHG-001..020.json)
/ui                Streamlit analyst dashboard
  /lib             Data loading (real cases via api.py), approval workflow, styling, graph-view builder
  /components      One module per dashboard section (queue, detail, evidence, confidence, actions, approvals)
  /tests           Dashboard robustness test suite (20 synthetic edge-case records)
api.py              Stable interface between the agent and the UI: run_case, get_case, list_pending_approvals, approve
run_benchmark.py    Runs the agent over case_pack.csv, writes cases/*.json
```

## Technology stack

| Layer | Tool | Status |
|---|---|---|
| UI | Streamlit + streamlit-agraph | **In use** |
| Graph database | TigerGraph Savanna / Community Edition | **Partially validated live** — schema/loading compile clean against real TigerGraph CE; the graded 20-case run used `backends/local.py` (same algorithms, real data, no live connection). See [TigerGraph's role](#tigergraphs-role). |
| Graph ↔ agent bridge | `mcp/tools.py` (tigergraph-mcp-shaped) | **In use** |
| Agent framework | LangGraph | **In use** (`agent/graph.py`) |
| LLM | Groq (primary) / Gemini (backup) / fixture (offline) | **In use** |
| Case memory | Graph-native prior-case retrieval + local cache | **In use** (`memory/`) |

## Prerequisites

- Python 3.11+ (developed against 3.13)
- `pip`
- A modern browser, to view the dashboard
- **Nothing else is required to view the dashboard or re-validate the 20 answer files** — no TigerGraph account, no LLM API key, no `.env` file needed for that. Re-running the agent against a live TigerGraph instance needs `TG_HOST`/`TG_USERNAME`/`TG_PASSWORD`/`TG_SECRET` (see `mcp/config.py`) and `GROQ_API_KEY`/`GOOGLE_API_KEY` for real LLM output; `GRAPH_BACKEND=local` + `LLM_MODE=fixture` (both `run_benchmark.py` defaults) need neither.

## Installation & setup

```bash
git clone https://github.com/ShriyaP1966/T1-TigerGraph.git
cd T1-TigerGraph
pip install -r requirements.txt -r ui/requirements.txt
```

## Running the application

```bash
cd ui
streamlit run app.py
```

Opens at `http://localhost:8501`. Renders the 20 real cases in `cases/` end to end — case queue, evidence, confidence, actions, graph view, and a live approval queue backed by the real policy ledger.

## Re-running the agent

```bash
python run_benchmark.py                              # all 20, resume if partially done
python run_benchmark.py --cases HHG-001,HHG-011       # just these
python run_benchmark.py --backend local --llm-mode fixture   # fully offline (the default)
python run_benchmark.py --backend tigergraph --llm-mode groq # against a live TigerGraph + Groq
```

Case memory (`memory/.cache/`) persists across runs by design. For a reproducible from-scratch run: `rm -f memory/.cache/added_cases.json memory/.cache/open_cases.json` first.

## Testing / QA

```bash
python ui/tests/test_dashboard_robustness.py       # dashboard vs. 20 synthetic edge-case records
python scripts/tests/test_validate_answer_file.py  # answer-file validator vs. a valid + a broken fixture
python scripts/validate_answer_file.py cases/       # the real 20 answer files — all pass
```

Neither test suite requires network access, a browser, or a running server.

## Benchmark cases

`case_pack.csv` lists the 20 real benchmark cases. `closed_cases_history.csv` is the labeled history (5,565 closed investigations) the agent uses as memory. `README1.md` is the full dataset README: task description, column definitions, the five known fraud patterns, the fraud policy (rules R1–R10), and the exact required answer-file format. All 20 answer files exist in `cases/` and pass `scripts/validate_answer_file.py`.

## Demo

See `DEMO_VIDEO_SCRIPT.md` for the shot-by-shot script (trigger → evidence gathering → uncertainty → requesting more evidence → action → explanation, plus a memory-reuse case).

## Current status

- [x] **Phase 0 — Align & set up.** Case-record JSON contract defined and validated, Streamlit skeleton scaffolded and running.
- [x] **Phase 1 — Policy doc prep.** Real fraud policy (`POL-001`–`019`), typologies (`TYP-001`–`005`), and regulatory references (`REG-001`–`010`) all chunked with real content.
- [x] **Phase 2 — Streamlit dashboard (core).** All views built and manually verified in-browser.
- [x] **Phase 3 — Live integration with the real agent.** `ui/lib/data.py` and `ui/lib/mock_actions.py` read/write through `api.py`; the approvals queue and decision log are backed by the real sqlite policy ledger.
- [x] **Phase 4 — QA of all 20 benchmark answer files.** All 20 pass `scripts/validate_answer_file.py` (required fields, enums, cross-field rules, approval-route policy checks, and ID cross-checks against `case_pack.csv`/`closed_cases_history.csv`).
- [ ] **Phase 5 — Demo video, blog post, social post.** Blog post and social post drafted (`BLOG_POST.md`, `SOCIAL_POST.md`); demo video script ready (`DEMO_VIDEO_SCRIPT.md`) — recording and publishing are the remaining human steps.

## Known limitations

- **The 20 graded answer files ran against `backends/local.py`, not a live TigerGraph instance.** The schema and loading jobs compile against real TigerGraph CE 4.2.5, but the full transaction load didn't finish (host ran out of RAM) and the derived-edges/case-writeback GSQL are untested live (one known bug in the latter). See [TigerGraph's role](#tigergraphs-role) for the exact status and what's left to close this out.
- `confidence_breakdown` (per-component confidence bars) only appears for cases run live in-process; reloading a case from its answer file alone can't recover that ephemeral state (see the dashboard section above)
- Regulatory references cover 5 of the ~15 sources README1.md links (FFIEC pages are bot-blocked from this environment; FATF's 6 reports and OFAC's SDN list were deprioritized as lower-relevance to card-fraud red flags specifically)
- `transactions.csv` (the ~708MB core transaction table) and other raw dataset inputs are gitignored, not committed — `data/processed/*.csv` is the loaded, derived data
- Conversational follow-up chat panel and public Streamlit Cloud deployment were explicitly out of scope (stretch goals, cut first per the task brief)

## License

No license file is currently included in this repository.

## Submission requirements (tracking)

- [x] Working agent (code in this repo)
- [ ] GitHub repository, shared with judges
- [x] One answer file per benchmark case (20 total): case record, evidence, findings, decisions, actions taken
- [x] Each case also written into the graph (`case.written_to_graph`) — written to the local graph-equivalent backend for all 20; not yet re-run against a live TigerGraph instance (see Known limitations)
- [x] Suspicious Activity Report generated when policy requires it
- [x] Next-best action + approval route recorded both before and after any additional evidence is gathered
- [ ] 3–5 minute demo video (script ready: `DEMO_VIDEO_SCRIPT.md`)
- [x] Technical blog post (`BLOG_POST.md`)
- [ ] Social post on X or LinkedIn tagging @TigerGraphDB (drafted: `SOCIAL_POST.md`, awaiting publish)

Submit at: https://forms.gle/yxXzqSULGgZ9VUF56 — one submission per team, by the team lead, by **Sept 24, 2026, 11:59 PM IST**. No resubmissions.

Support: TigerGraph Discord https://discord.gg/7JMkCAy9D3
