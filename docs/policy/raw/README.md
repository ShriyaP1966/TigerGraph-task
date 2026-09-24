# Raw policy source documents — drop the real dataset files here

This folder is the input to `scripts/chunk_policy_docs.py`. It is **empty of
real content** because the HHGOA_IEEE dataset (which contains the bank's
actual fraud policy, the five known fraud typologies, and the regulatory
references) has not been downloaded into this repo yet.

## What to do

1. Get the dataset from the link in the hackathon brief (the `HHGOA_IEEE`
   reference in `TigerGraph Agentic Fraud Investigation HHGOA.pdf`).
2. **Read its README first** — it defines the exact answer format, column
   meanings, and how cases work. Don't build further against assumptions
   once it's available.
3. Convert/copy the policy document into `policy/`, the fraud typology
   document into `typology/`, and any regulatory reference material into
   `regulatory/`, as plain text or Markdown files, with `##` headings marking
   each distinct clause/typology/reference. (If the source is a PDF, extract
   its text first — see the `pdf` skill / `pdftotext` / `pdfplumber`.)
4. Re-run `python scripts/chunk_policy_docs.py` — it will pick up the new
   files automatically and (re)generate `docs/policy/chunks/*.json` with
   stable IDs.

## Current state

Each subfolder currently contains one `SAMPLE_*` file with illustrative,
generic banking-fraud content (NOT from the real dataset) so the chunking
pipeline, ID scheme, and downstream GraphRAG/graph-loading code can be built
and tested end-to-end today. **Delete or replace the `SAMPLE_*` files once
the real dataset is in hand** — do not ship sample content in the final
submission.
