# HHGOA — TigerGraph Agentic Fraud Investigation

An agentic fraud investigation system built on TigerGraph for the Hacker House Goa hackathon. Given a trigger (risk score / customer report / analyst request), a LangGraph agent investigates the transaction graph and prior closed cases, decides whether it has enough evidence to reach a verdict, requests more evidence when it doesn't, recommends policy-compliant next-best actions, explains its reasoning with cited evidence and policy clauses, and writes the case back into the graph as memory for future investigations.

## Architecture

```
IEEE-CIS data ─┐
Fraud policy   ─┼─▶ TigerGraph ─▶ graph/mcp/tools.py ─▶ LangGraph agent ─▶ api.py ─▶ Streamlit UI
Typologies     ─┤   (schema +      (7-tool MCP          (agent/graph.py)   (stable      (case queue,
Prior cases    ─┘    derived        contract,                              interface)   evidence,
                      fraud-ring     fixture/live)                                       approvals,
                      edges)                                                             graph view)
```

## How TigerGraph is used

- **Schema** (`graph/schema/01_schema.gsql`): `Customer`, `Card`, `Transaction`, `DeviceProfile`, `EmailDomain`, `BillingRegion` from the IEEE-CIS data, plus `ClosedCase`/`InvestigationCase` as graph-native case memory.
- **Derived edges** (`graph/algorithms/03_derived_edges.gsql`): `SHARES_DEVICE`/`SHARES_EMAIL`/`SHARES_ADDRESS` build the fraud-ring backbone between cards, each cardinality-capped so a commonly-shared attribute (a popular email domain, a common device fingerprint) can't blow up into a meaningless thousands-member "ring". `graph/queries/device_ring.gsql` isolates a seed card's genuinely *rare* shared device(s) specifically — the query behind HHG-014's device-linkage detection.
- **Investigation queries** (`graph/algorithms/04_graph_queries.gsql`): account subgraph, fraud-ring membership, transaction velocity, prior similar cases, policy context, shortest path — six queries backing a locked 7-tool MCP contract (`contracts/mcp_tool_contracts.json`).
- **Case write-back** (`graph/case_memory/05_case_writeback.gsql`): each finished investigation writes back as a graph vertex, making case memory a graph traversal rather than a bolted-on vector store.

## Results

Full 20-case benchmark, `GRAPH_BACKEND=tigergraph`, `LLM_MODE=fixture`: **10 fraud / 6 legitimate / 4 uncertain**. SAR filed on 2 cases — **HHG-014** (undocumented coordinated-abuse pattern via the device-ring query, R9) and **HHG-010** (exposure over $1,000, section 3a). All 20 pass `scripts/validate_answer_file.py` and are confirmed written to the graph.

## Quickstart

```bash
git clone https://github.com/ShriyaP1966/TigerGraph-task.git
cd TigerGraph-task
pip install -r requirements.txt
cp .env.example .env   # fill in TG_HOST/TG_USERNAME/TG_PASSWORD/TG_SECRET + GROQ_API_KEY to run live; skip for offline defaults

cd ui && streamlit run app.py   # dashboard at http://localhost:8501, renders cases/*.json

python run_benchmark.py --backend local --llm-mode fixture   # fully offline rerun (default)
python run_benchmark.py --backend tigergraph --llm-mode fixture   # against the live graph

python scripts/validate_answer_file.py cases/   # re-validate the 20 answer files
```

## Repository structure

```
/agent        LangGraph agent (graph.py, nodes.py, patterns.py, rules.py)
/graph        TigerGraph schema, loading jobs, GSQL queries, case write-back, MCP tool layer
/backends     GraphBackend implementations: mock, local, tigergraph
/llm          LLM client (Groq / Gemini / fixture modes)
/scoring      Confidence engine
/policy       Policy table + approval gate (auto/L1/L2 routing)
/actions      sqlite action ledger
/memory       Case-memory cache/retrieval
/contracts    Case-record + Answer Format contracts, ui_adapter.py
/docs/policy  Chunked policy/typology/regulatory content (GraphRAG source)
/scripts      Policy chunker, answer-file validator, benchmark scripts + tests
/cases        The 20 graded answer files (HHG-001..020.json)
/ui           Streamlit analyst dashboard
api.py            Stable interface between the agent and the UI
run_benchmark.py  Runs the agent over case_pack.csv, writes cases/*.json
```

## Docs

- [`DATASET_README.md`](DATASET_README.md) — the task's dataset spec: answer format, fraud policy (R1–R10), and the 20-case exam pack.
- [`BLOG_POST.md`](BLOG_POST.md) — build write-up: what we built, how TigerGraph is used, what we learned, what we'd improve.
- Demo video: [DEMO_URL]

## Known limitations

- **Templated, not model-written, explanations by default.** `LLM_MODE=fixture` (the mode the graded run used) builds case summaries and SAR narratives from a deterministic template over real evidence, not an LLM call.
- **A custom, `tigergraph-mcp`-shaped tool layer, not the official server** — `graph/mcp/tools.py` matches the same contract, hand-implemented against `pyTigerGraph`.
- **TF-IDF similar-case retrieval, not TigerGraph's native vector search** — a `pyTigerGraph`/GSQL `VERTEX<T>` parameter-encoding issue makes the live call fall back automatically; structural ring retrieval is unaffected.
- **Evidence and actions aren't separate graph vertices in the live write-back** — this GSQL edition doesn't support `TUPLE`/`JSONARRAY` as query parameter types, which the original per-evidence/per-action vertex design relied on. The case itself, its verdict/pattern, and its memory edges still write correctly.

See `BLOG_POST.md` for the full list and reasoning.

## Team

- P1 (graph & knowledge engineering)
- P2 (agent & backend engineering)
- P3 (UI, GraphRAG docs, demo, final fixes) — Shriya Patil ([@ShriyaP1966](https://github.com/ShriyaP1966))

## License

MIT — see [`LICENSE`](LICENSE). The underlying dataset (IEEE-CIS/Vesta, distributed via the TigerGraph Hacker House Goa hackathon) is under its own terms.
