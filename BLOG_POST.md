# Building an agentic fraud investigator on TigerGraph — and giving it a memory that's actually a graph

*Technical blog post for the HHGOA (Hacker House Goa) TigerGraph Agentic Fraud Investigation hackathon.*

## What we built

Banks get uncertain fraud signals constantly: a risk-scoring model flags a transaction, a customer disputes a charge, an analyst asks for a second look. Every one of those needs the same treatment — investigate, decide if there's enough evidence, gather more if there isn't, take a policy-compliant action, explain the reasoning, and remember the case so the next one benefits from it.

We built an agent that does exactly that against the IEEE-CIS transaction dataset, a written fraud policy (10 numbered rules, five known fraud typologies), and 5,565 closed historical cases. Given a trigger from `case_pack.csv`, it investigates the transaction graph, computes a transparent confidence score, decides whether it can act or needs more evidence, routes any high-impact action through an approval gate, writes a full explanation citing its evidence and policy clauses, and persists the case back into the graph as memory. It ran end to end over all 20 benchmark cases and produced one structured answer file per case — all 20 pass our own format validator, which checks required fields, enums, and every cross-field rule the dataset spec states (SAR/action agreement, approval-route policy, made-up-ID detection against the real case files).

An analyst-facing Streamlit dashboard sits on top: case queue, evidence timeline, confidence breakdown, a graph view of the relevant subgraph, and a real approval queue for actions that need human sign-off before they execute.

## Architecture

```
IEEE-CIS data ─┐
Fraud policy   ─┼─▶ TigerGraph ─▶ mcp/tools.py ─▶ LangGraph agent ─▶ api.py ─▶ Streamlit UI
Typologies     ─┤   (graph +      (7-tool          (trigger → evidence →         (case queue,
Prior cases    ─┘    fraud-ring    contract,         confidence → uncertainty     evidence,
                      edges,       fixture/live)      gate → actions → approval    approvals,
                      GSQL algos)                     → explain → memory write)    graph view)
```

Three layers, cleanly separated by a JSON contract at each boundary:

- **Graph layer** — TigerGraph schema (`Customer`, `Card`, `Transaction`, `DeviceProfile`, `EmailDomain`, `BillingRegion`, plus `ClosedCase`/`InvestigationCase` for memory), derived fraud-ring edges (`SHARES_DEVICE`/`SHARES_EMAIL`/`SHARES_ADDRESS`), and six GSQL investigation queries plus a write-back job, all exposed through a locked 7-tool MCP contract.
- **Agent layer** — a LangGraph state machine with an explicit uncertainty loop, a deterministic (non-LLM) confidence engine, and a policy gate that re-derives the approval route from a policy table rather than trusting whatever the LLM said.
- **UI layer** — a Streamlit dashboard that renders exactly the fields a case record contract defines, nothing invented, so a real agent's output renders correctly without UI changes.

`api.py` is the frozen interface between the agent and the UI (`run_case`, `get_case`, `list_pending_approvals`, `approve`) — the dashboard never touches the graph, the LLM, or the ledger directly.

## How TigerGraph is used

The graph isn't just storage for this project — it's the mechanism for two of the system's core claims, expressed as GSQL first and validated at two different levels: the schema/query logic against a real TigerGraph instance, and the end-to-end behavior against a same-algorithm local backend.

**Fraud-ring detection is a graph traversal.** `03_derived_edges.gsql` builds shared-device/email/address edges between cards as a self-join over the loaded transaction data, and `04_graph_queries.gsql`'s `find_fraud_ring` runs weakly-connected-components over that backbone. One of our 20 cases (`HHG-008`) resolves to a 21-member cluster with 19 known-fraud members — that's a structural signal no single-transaction risk score can see.

**Case memory is a graph traversal too, not a side vector DB.** Every finished investigation gets written back as an `InvestigationCase` vertex (`05_case_writeback.gsql`). We proved this loop closes, not just that the code compiles: we ran a synthetic case (`DEMO-B`) before and after writing `HHG-015` into the graph. Before, its top similar prior cases were three entries from the closed-case history. After, `HHG-015` itself appears as the #2 most similar case (similarity 0.4419) — the agent retrieved a case it had investigated minutes earlier, purely from a graph query, with no separate embedding store to keep in sync.

**Honest status on TigerGraph execution**: the schema and loading jobs compile clean against a real TigerGraph Community Edition 4.2.5 instance (Docker), and dimension tables load with 0 errors. The full transaction load, the derived fraud-ring edges, and the case-writeback query are written for TigerGraph but not yet validated end-to-end against a live instance — the Docker host ran out of RAM partway through the transaction load, and `05_case_writeback.gsql` has one known bug (an undefined reverse-edge reference) flagged for the next fix. The 20 graded cases above, and the fraud-ring/memory numbers cited, ran against `LocalBackend` — a pandas + NetworkX reimplementation of the exact same connected-components and retrieval logic, over the same real IEEE-CIS-derived data, behind the identical tool interface (`mcp/tools.py`'s `fixture`/`live` split, `backends/`'s `mock`/`local`/`tigergraph` split). The graph-native *design* is real and algorithmically identical either way; what's not yet proven is that specific 21-member cluster coming out of a live TigerGraph query rather than its local equivalent.

The agent reaches all of this through `mcp/tools.py`, switchable between a `fixture` mode (canned, contract-shaped responses, zero network dependency) and `live` mode against a real TigerGraph instance; `backends/tigergraph.py` implements the live path and is connected and timeout-tuned against a real instance, independent of the graded run's backend choice above.

## Agentic capabilities

**Confidence is a named, weighted sum, not a black box.** Every case's score is `0.30 × bank_risk_score + 0.30 × typology_match_strength + 0.25 × similarity_to_confirmed_fraud + 0.15 × evidence_coverage`, each component computed deterministically from evidence (no LLM in the scoring path — the LLM only writes the explanation afterward). The dashboard renders these four numbers as labeled bars, not a single opaque percentage.

**The uncertainty gate actually branches and loops.** `HHG-001` is a good example: a transaction risk-scored at 0.61 produces an initial confidence of 0.5683 — above "monitor," below "act" — so the agent requests step-up authentication and customer validation instead of guessing. Both come back clean (auth passed, customer confirms the purchase), and confidence resolves to 0.4783; policy rule R3 (a direct customer confirmation) then overrides what the raw score alone would suggest, and the case closes with no fraud finding. The answer file records *both* the before and after next-best-action, exactly as the grading format requires — you can see the agent change its mind in the data, not just read a final verdict.

**Actions are policy-gated, not agent-decided.** The agent proposes an action and a route, but `policy/gate.py` re-derives the real route from a policy table keyed on the action and the case's exposure amount — the agent's opinion is never trusted for the routing decision. `BLOCK_CARD` is auto-conditional on a $2,500 threshold; `BLOCK_ALL_CARDS` and `FILE_REPORT` are always L2 (fraud-manager sign-off). In `HHG-008`, that produces a real, mixed approval queue in one case: `BLOCK_CARD` at L1, `FILE_REPORT` at L2, alongside auto-executed monitoring of connected cards — exactly the "operate within predefined policies and permissions" requirement, made literal as a pending-actions queue an analyst clicks Approve/Reject on.

**Explanations cite their evidence and their policy clause.** `HHG-008`'s summary doesn't say "this looks suspicious" — it says the activity is consistent with account takeover (POL-004), names the fraud-ring size, and names the closest confirmed-fraud prior case with its similarity score. Every SAR narrative, when one is filed, inherits the same evidence-first structure.

## What we learned

- **A deterministic confidence engine is worth the discipline of keeping the LLM out of it.** It's trivially unit-testable, and it means the score can't silently drift just because a prompt changed — only the weights or the underlying evidence can move it.
- **Re-deriving the approval route instead of trusting the agent's stated route** caught real bugs early (an LLM confidently asserting the wrong route for a borderline-exposure `BLOCK_CARD` case) and made the policy engine the actual source of truth, which is what a real compliance reviewer would want anyway.
- **Contracts-first cross-team splitting paid off.** The agent (Answer Format) and the UI (a separate, richer case-record schema) are genuinely different shapes for the same investigation — evidence with stable IDs, per-component confidence, a decision log with status — and having `contracts/ui_adapter.py` as an explicit, documented, lossy mapping between them meant the UI could be built and stress-tested against 20 synthetic edge cases well before the agent existed, instead of the two sides discovering the mismatch under deadline pressure.
- **Reload paths need as much thought as the live path.** The dashboard's live-run path captures rich ephemeral state (per-evidence timestamps, confidence breakdown) that the graded Answer Format was never meant to carry. Reloading a case from disk days later can't magically recover state that was never persisted — the honest fix was to reconstruct everything the Answer Format *does* carry (evidence, findings, connected entities, final actions) and leave the genuinely-gone fields empty rather than fabricate them.

## What we'd improve

- **Templated, not model-written, explanations by default.** `LLM_MODE=fixture` — the mode the graded run actually used — builds every case summary and SAR narrative from a deterministic Python template over real evidence, not an LLM call. It's honest (no hallucination risk) and every field is real, but the prose is templated, not reasoned. Groq/Gemini integration exists and is a one-flag switch (`LLM_MODE=groq`), but wasn't the mode used for the submitted 20.
- **A custom, `tigergraph-mcp`-shaped tool layer, not the official server.** `graph/mcp/tools.py` matches the same 7-tool contract (`contracts/mcp_tool_contracts.json`) the official `tigergraph-mcp` project defines, hand-implemented against `pyTigerGraph` rather than running that server directly — a scope call made early, not a limitation we hit late.
- **TF-IDF similar-case retrieval, not TigerGraph's native vector search.** `get_prior_similar_cases` falls back to a local TF-IDF/cosine implementation over `closed_cases_history.csv` — partly a scope call, partly because a parameter-encoding issue between `pyTigerGraph` and this GSQL edition's `VERTEX<T>` query parameters causes the live call to fail and fall back automatically on every case. Structural retrieval (device-ring membership) is unaffected since it doesn't depend on that call.
- **Evidence and actions aren't separate graph vertices in the live write-back.** The original design (and the `Evidence`/`Action` vertex types, still in the schema) called for `write_case_to_graph` to create an `Evidence` vertex per claim and a `RECOMMENDS` edge per action. We had to drop those two parameters live: this GSQL edition doesn't support `TUPLE` or `JSONARRAY` as *query parameter* types (only inside a query body), which the original signature relied on. The case, its status/verdict/pattern, and its `SIMILAR_TO` memory edges still write correctly — it's specifically the fine-grained evidence/action vertices that are pending a redesign (most likely: flatten to delimiter-encoded `SET<STRING>` parameters, the one collection type proven to work here).
- **Persist the confidence breakdown**, not just the final score, in the Answer Format or a sidecar file, so any case can be fully reconstructed from disk without re-running the agent.
- **Finish the regulatory-reference chunking** — we covered 5 FinCEN documents in depth; FATF's cross-border-laundering reports and the FFIEC manual (bot-blocked from our fetch environment) are lower-relevance to card-present/card-not-present fraud specifically but would round out the GraphRAG citation set.
- **A conversational follow-up panel** where an analyst can ask the agent questions about a specific case, reusing the same tool layer live rather than only at investigation time — explicitly scoped out as the first cut if we ran short on time, and we did cut it.
- **Concurrent-approval race handling** — our approval API doesn't yet stop two analysts from resolving the same pending action simultaneously; the real endpoint should return a conflict instead of silently letting the second write win.

---

Repo: [github.com/ShriyaP1966/TigerGraph-task](https://github.com/ShriyaP1966/TigerGraph-task)
