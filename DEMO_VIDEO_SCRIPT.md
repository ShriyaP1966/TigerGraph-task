# Demo video script (target 3:30–4:30)

Two real cases from `cases/`, no invented data. Primary case (`HHG-008`) covers the
full required arc in one investigation: trigger → evidence gathering → uncertainty →
requesting more evidence → action → explanation. Second case (`HHG-015` / the
`DEMO-B` pair) proves case-memory reuse.

**Setup before recording**: `rm -f ledger.sqlite3 ui/.local/audit_ledger.json` (clean
approval state, so the Approve click in Shot 5 is real, not already-resolved), then
`cd ui && streamlit run app.py`.

Roles: one person drives the UI/mouse, one narrates. Record screen + voice together if
solo.

---

## Shot 1 — Cold open (0:00–0:20)

**Screen**: Case Queue, full table visible.

**Narration**:
> "This is an agentic fraud investigator built on TigerGraph. Given an uncertain
> signal — a risk score, a customer dispute, an analyst request — it investigates
> the transaction graph, decides if it has enough evidence to act, asks for more if
> it doesn't, takes a policy-compliant action, and explains itself. Twenty real
> benchmark cases, all in this queue."

Point at the confidence column and status badges as you say it.

## Shot 2 — Trigger (0:20–0:45)

**Screen**: Click into `HHG-008`. Case header + trigger panel visible.

**Narration**:
> "Case HHG-008: a customer report. 'I never made this $55.68 purchase' — flagged
> transaction 3558054. That's the trigger. No fraud verdict yet, just a question the
> agent has to go investigate."

## Shot 3 — Evidence gathering + fraud-ring graph (0:45–1:40)

**Screen**: Evidence & Findings tab, then switch to the Graph tab.

**Narration**:
> "The agent pulls transaction history, velocity checks, and — this is the graph-
> native part — shared device, email, and address links between cards. For this
> case, that traversal surfaces a 21-member cluster, 19 of them already known
> fraud. That's not a rule someone wrote for 'clusters of exactly this shape' — it's
> a weakly-connected-components query over derived edges, the same graph algorithm
> we wrote in GSQL for TigerGraph, run here through our local graph backend over
> the real transaction data."

Show the graph view rendering the case's subgraph live.

**Accuracy note (don't skip)**: say "local graph backend," not "TigerGraph," for
this specific number — the GSQL fraud-ring query (`03_derived_edges.gsql`) is
written but not yet run against a live TigerGraph instance (transaction load
didn't finish loading there; see `graph/README.md`). The local backend runs the
identical connected-components logic over the same real data, so the finding
itself is genuine — just don't claim TigerGraph produced this exact number live,
since it didn't for this submission.

## Shot 4 — Uncertainty (1:40–2:15)

**Screen**: Confidence tab. Point at the four labeled bars and the score.

**Narration**:
> "Confidence isn't one opaque number. It's four named, weighted components — bank
> risk score, typology match, similarity to confirmed fraud, evidence coverage —
> and right now they add up to 0.52. The policy threshold to act is 0.75. Below
> that, the agent doesn't guess — it asks for more evidence instead."

Switch to Actions & SAR tab, show `next_best_action.before_additional_evidence` =
`CREATE_CASE` / `FILE_REPORT` / `MONITOR_CONNECTED_CARDS` (no block yet).

## Shot 5 — Requesting more evidence, and the action changing (2:15–2:50)

**Screen**: Stay on Actions & SAR tab, scroll to show the "after additional evidence" side.

**Narration**:
> "It requested customer validation. The customer responded: they didn't make the
> purchase and still have the card in hand — so this isn't a lost-card case, it's
> account takeover. That single answer moves confidence from 0.52 to 0.70, and the
> recommended action changes: BLOCK_CARD gets added. You can see both the before
> and after right here in the same record — the agent visibly changing its mind."

## Shot 6 — Action + approval gate (2:50–3:30)

**Screen**: Navigate to Approvals in the sidebar (point at the live "N pending" badge
first). Show HHG-008's pending items.

**Narration**:
> "High-impact actions don't just execute. BLOCK_CARD needs a level-1 approval,
> FILE_REPORT — because this links to a confirmed fraud ring — needs level-2,
> fraud-manager sign-off. Both sit in a real pending queue, backed by the same
> sqlite policy ledger the agent itself writes to. I click Approve—"

Click **Approve** on one pending item live. Point out the status badge flipping to
"Executed" and the decision log updating on the case detail page.

## Shot 7 — Explanation (3:30–3:55)

**Screen**: Case Detail → explanation / SAR section.

**Narration**:
> "And the explanation isn't 'this looks suspicious.' It cites its evidence IDs, the
> exact policy clause — POL-004, account takeover — and the closest confirmed-fraud
> prior case with its similarity score. A Suspicious Activity Report gets generated
> automatically because the policy requires one here."

## Shot 8 — Memory reuse, the second case (3:55–4:30)

**Screen**: Either show `HHG-015`'s case detail (Case memory tab) briefly, then cut
to (or read from) `scripts/demo_case_memory_output.json`.

**Narration**:
> "Last thing: case memory isn't a side vector database, it's a graph traversal. We
> ran a synthetic case before HHG-015 existed in memory — its top similar prior
> cases were three closed historical cases. We ran the exact same case again after
> writing HHG-015 back — and HHG-015 itself now shows up, ranked second, similarity
> 0.44. The agent retrieved an investigation it had just finished, purely from a
> graph query against the same case-writeback logic we wrote for TigerGraph."

**Accuracy note (don't skip)**: this demo, like Shot 3, ran on the local graph
backend, not a live TigerGraph instance — `05_case_writeback.gsql` (the live
write-back query) has one known bug and hasn't been run against a real TigerGraph
instance yet. Say "graph traversal" / "graph query," not "TigerGraph," when
describing this specific result.

## Closing (4:30–4:40)

**Narration**:
> "TigerGraph for the transaction graph and the memory, LangGraph for the agent,
> a deterministic policy and confidence engine so the numbers can't silently
> drift, and a dashboard that renders exactly what the agent produces. Thanks."

---

## Recording checklist

- [ ] `rm -f ledger.sqlite3 ui/.local/audit_ledger.json` before recording (clean approval state)
- [ ] `streamlit run ui/app.py`, confirm all 20 cases load in the queue
- [ ] Screen resolution readable at 1080p; zoom browser to ~110–125% for text legibility
- [ ] Practice the Approve-button click once off-camera so it's not fumbled live
- [ ] Keep total runtime inside 3–5 minutes per the submission requirement
- [ ] Export/upload, then fill `[DEMO_URL]` into `SOCIAL_POST.md` and this repo's README
