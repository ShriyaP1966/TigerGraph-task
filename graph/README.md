# P1 — TigerGraph Fraud Investigation Graph

**Track:** P1 (graph layer) for the TigerGraph × Hacker House Goa fraud investigation exam. This repo owns the schema, ETL, loading jobs, derived fraud-ring edges, investigation queries, case write-back, and the MCP (Model Context Protocol) tool contract that the P2 agent calls against.

The dataset, task, fraud policy, and answer format this graph was built to support are the IEEE-CIS-based Hacker House Goa exam dataset (`data/raw/README.md` has the full copy: patterns, regulatory references, the 20-case exam pack, and the required answer JSON schema).

## Status

**Schema, ETL, loading jobs, derived edges, GDS/investigation queries, the write-back job, and the MCP contract + fixtures are all written.**

The P1 graph is being used with the **TigerGraph cloud/GCP environment**, rather than a local Docker-based TigerGraph Community Edition setup.

The Python MCP layer works today in `fixture` mode with no graph connection required, so this doesn't block P2.

The remaining validation work is focused on running and checking the GSQL against the active TigerGraph cloud/GCP instance.

The reverse-edge definitions required by the case-memory and investigation queries have also been added:

```text id="74216"
ON_CARD → reverse_ON_CARD
CASE_INVOLVES_CARD → reverse_CASE_INVOLVES_CARD
```

## Repo layout

```text id="18034"
contracts/
  mcp_tool_contracts.json   The published MCP tool I/O contract (7 tools)

data/
  raw/                      Source CSVs (gitignored — not in repo, see below)
  processed/                ETL output CSVs (gitignored — regenerated, not committed)

graph/
  schema/01_schema.gsql              Vertex / edge / graph definitions
  loading/02_loading_jobs.gsql       GSQL LOADING JOB definitions
  loading/prepare_data.py             ETL: raw CSVs -> load-ready CSVs
  loading/*.tsv                       Policy / typology / action reference data
  algorithms/03_derived_edges.gsql    SHARES_DEVICE / SHARES_EMAIL / SHARES_ADDRESS builders
  algorithms/04_graph_queries.gsql    Investigation queries (see below)
  case_memory/05_case_writeback.gsql  write_case_to_graph — the case-memory write path
  README.md                           Full schema doc + reload-from-scratch instructions

mcp/
  config.py
  tools.py
```

## Data model

**Vertices:** `Customer`, `Card`, `Transaction`, `DeviceProfile`, `EmailDomain`, `BillingRegion`, `ClosedCase` (immutable historical case memory), `InvestigationCase` (cases this agent creates/updates), `Evidence`, `PolicyClause`, `FraudTypology`, `Action`.

**Key edges:** `Customer -OWNS-> Card`, `Card -MADE-> Transaction`, `Transaction -FROM_DEVICE-> DeviceProfile`, `Transaction -PURCHASER_EMAIL-> EmailDomain`, `Transaction -BILLED_IN-> BillingRegion`, plus derived fraud-ring backbone edges `Card <-SHARES_DEVICE/SHARES_EMAIL/SHARES_ADDRESS-> Card` built by `03_derived_edges.gsql`.

Full rationale for every modeling decision (why V1-V339 aren't loaded, how `card_id` is derived when `transactions.csv` doesn't have one, why shared-email/address edges are capped by `max_cards`, etc.) is in `graph/README.md`.

## Investigation queries (`algorithms/04_graph_queries.gsql`)

| Query                         | Purpose                                                                        |
| ----------------------------- | ------------------------------------------------------------------------------ |
| `get_account_subgraph`        | Full local context for one card: owner, transactions, shared links             |
| `find_fraud_ring`             | Weakly-connected-components over the shared-device/email/address backbone      |
| `get_transaction_velocity`    | Count/sum of transactions in a rolling window (card-testing / burst detection) |
| `get_prior_similar_cases`     | Retrieves closed cases similar to a card/pattern (structural + semantic)       |
| `get_policy_context`          | Structured retrieval of policy clauses + typology descriptions by topic        |
| `shortest_path_between_cards` | Path between two cards over the fraud-ring backbone                            |

Plus `write_case_to_graph` (`case_memory/05_case_writeback.gsql`), which writes an investigation's case, evidence, and actions back into the graph as case memory for future retrieval.

## MCP tool layer

`contracts/mcp_tool_contracts.json` is the locked I/O contract for 7 tools (the 6 queries above plus `write_case_to_graph`).

`mcp/tools.py` implements it in two modes, switched by the `MCP_MODE` environment variable:

* **`fixture`** (default) — returns realistic, contract-shaped example data with no graph connection. This is what P2 can build against today.
* **`live`** — connects to the active TigerGraph instance via `pyTigerGraph` and calls the installed queries.

Connection settings (`mcp/config.py`) are environment-variable driven:

```text id="mw9q9s"
TG_HOST
TG_GRAPH
TG_USERNAME
TG_PASSWORD
TG_SECRET
TG_GS_PORT
TG_REST_PORT
MCP_MODE
```

The same graph layer can therefore be used with the active TigerGraph cloud/GCP environment without changing the graph implementation.

## About `data/`

`data/raw/` and `data/processed/` are **gitignored and not committed** to this repo (the raw exam dataset is large and distributed separately by the Hacker House Goa organizers).

To reproduce locally:

1. Obtain the dataset (`transactions.csv`, `identity.csv`, `closed_cases_history.csv`, `case_pack.csv`) and place it under `data/raw/`.
2. `data/raw/README.md` documents the exact file layout, columns, and license terms.
3. Run the ETL:

```bash id="70v1t6"
python graph/loading/prepare_data.py
```

## Reload from scratch

See `graph/README.md` for the full copy-pasteable sequence for preparing the data, loading the schema, running loading jobs, building derived edges, installing queries, installing the case write-back query, and connecting the MCP layer to the TigerGraph instance.

The active setup uses the **TigerGraph cloud/GCP environment** rather than a local Docker deployment.

The general sequence is:

```text id="8w3s5b"
python graph/loading/prepare_data.py

Load / install the schema in the TigerGraph cloud environment

Run the required loading jobs

Run the derived-edge builders

Install the investigation queries

Install the case write-back query

Configure MCP_MODE=live

Configure the TigerGraph cloud connection details
```

## Handoff to P2

P2's agent should call the 6 read queries as MCP tools to gather evidence per case (from `case_pack.csv`) and call `write_case_to_graph` to persist each finished investigation as case memory for the next one.

The exam's answer format, fraud policy, and the 20 case pack rows are documented in full in `data/raw/README.md`.
