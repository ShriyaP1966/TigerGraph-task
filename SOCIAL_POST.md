# Social post drafts

Fill in `[BLOG_URL]` and `[DEMO_URL]` once the blog post is published (e.g. as a GitHub repo page / Medium / dev.to) and the demo video is uploaded (e.g. YouTube/Drive link), then post one of these to X or LinkedIn. Tag @TigerGraphDB either way.

## X / Twitter (under 280 chars)

```
We built an agentic fraud investigator on @TigerGraphDB for #HackerHouseGoa 🕵️‍♀️📊

Confidence scores you can see the math behind. Fraud rings found by graph traversal. Case memory that's literally a graph query, not a side vector DB.

Blog: [BLOG_URL]
Demo: [DEMO_URL]
```

## LinkedIn (longer)

```
We just shipped an agentic fraud investigation system on TigerGraph for the Hacker House Goa hackathon — and I wanted to share what made it fun to build.

The agent takes an uncertain fraud signal (a risk score, a customer dispute, an analyst request), investigates the transaction graph, decides if it has enough evidence to act, and if not, asks for more — step-up auth, customer validation, analyst input — before recommending a policy-compliant next action. High-impact actions (freezing a card, filing a report) sit in a real approval queue until a human signs off.

A few things I'm proud of:

🔍 Confidence is a named, weighted score (bank risk, typology match, similarity to past fraud, evidence coverage) rendered as labeled bars — not a black-box number.

🕸️ Fraud rings are found by a graph traversal over shared device/email/address edges, not a heuristic rule. One of our 20 benchmark cases resolved to a 21-member cluster with 19 known-fraud members.

🧠 Case memory lives in the graph model itself, not a side vector database. We proved it: ran the same synthetic case before and after writing a real investigation back into case memory, and the new case showed up as a retrieved "similar prior case" on the second run — same query logic we wrote in GSQL for TigerGraph.

📋 Every recommendation cites its evidence and its policy clause — the explanation reads like an auditor wrote it.

Built with TigerGraph @TigerGraphDB, LangGraph, and a deterministic (non-LLM) confidence + policy engine so the numbers and routing decisions can't silently drift.

Full technical writeup: [BLOG_URL]
Demo video: [DEMO_URL]

#TigerGraph #GraphDatabase #AgenticAI #FraudDetection #HackerHouseGoa
```
