# Raw policy source documents

This folder was the input to `scripts/chunk_policy_docs.py`. The real
HHGOA fraud policy, the five known fraud typologies, and regulatory
reference material (5 FinCEN documents) were extracted, chunked, and
committed to `docs/policy/chunks/` — see `PERSON3_PROGRESS.md` (Phase 1)
for exactly what was fetched and why some DATASET_README.md-linked sources
(FFIEC, FATF, OFAC's SDN list) weren't. No `SAMPLE_*` placeholder content
ships in this repo.

The intermediate raw source files themselves (`policy/`, `typology/`,
`regulatory/` subfolders) are not committed — `docs/policy/chunks/*.json`
is the real deliverable P1 loads as graph vertices and the UI cites.

## Re-chunking

If a raw source file is restored/edited, re-run:

```bash
python scripts/chunk_policy_docs.py
```

It regenerates `docs/policy/chunks/{policy_clauses,typologies,regulatory_references}.json`.
IDs are cached in `docs/policy/chunks/_id_map.json` and won't shift when a
doc is edited or a new one is added.
