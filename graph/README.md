# graph/

TigerGraph schema, ETL, GSQL queries, and case write-back for the fraud
investigation graph.

- `schema/01_schema.gsql` — vertex/edge/graph definitions.
- `loading/` — `02_loading_jobs.gsql` (LOADING JOB defs), `prepare_data.py` (raw CSVs → load-ready CSVs), policy/typology/action reference `.tsv` files.
- `algorithms/03_derived_edges.gsql` — builds the `SHARES_DEVICE`/`SHARES_EMAIL`/`SHARES_ADDRESS` fraud-ring backbone.
- `algorithms/04_graph_queries.gsql` — the 6 investigation queries backing `contracts/mcp_tool_contracts.json` (account subgraph, fraud ring, velocity, similar cases, policy context, shortest path).
- `queries/` — standalone GSQL: `device_ring.gsql` (cardinality-capped shared-device detection) plus copies of the `build_shares_*`/`get_prior_similar_cases`/`write_case_to_graph` queries, for ad hoc install/testing outside the numbered pipeline.
- `case_memory/05_case_writeback.gsql` — `write_case_to_graph`, the case-memory write path.
- `mcp/` — `graph/mcp/tools.py` implements the 7-tool MCP contract (`fixture`/`live` modes via `pyTigerGraph`); `config.py` holds `TG_*` connection settings.
- `export/all_queries_live_export.gsql` — a full export snapshot of every installed query, for reference/backup.

**To reload from scratch**: run `prepare_data.py`, install `schema/01_schema.gsql`, run the loading jobs, run `algorithms/03_derived_edges.gsql`, install `algorithms/04_graph_queries.gsql` and `case_memory/05_case_writeback.gsql`, then point `graph/mcp/config.py` (`TG_HOST`/`TG_USERNAME`/`TG_PASSWORD`/`TG_SECRET`) at the instance and set `MCP_MODE=live`.
