"""Builds graph/loading/{policy_clauses,typologies}_chunked.tsv from the real
chunked docs (docs/policy/chunks/{policy_clauses,typologies}.json), matching the
existing load_policy_typology_action job's expected columns (clause_id/text,
typology_id/description). These are additive: their IDs (POL-*/TYP-*) are a
different namespace from the existing R1-R10 / pattern-name PolicyClause and
FraudTypology vertices, so loading them upserts new vertices without touching
the old ones.

Usage: python graph/loading/build_chunked_policy_typology_tsv.py
"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _clean(s: str) -> str:
    # TSV-safe: collapse embedded tabs/newlines so each chunk stays one row.
    return " ".join(s.split())


def build(src_name: str, id_field: str, out_name: str, header: tuple[str, str]) -> int:
    src = REPO_ROOT / "docs" / "policy" / "chunks" / src_name
    chunks = json.loads(src.read_text(encoding="utf-8"))
    out = REPO_ROOT / "graph" / "loading" / out_name
    lines = ["\t".join(header)]
    for c in chunks:
        text = _clean(f"{c['title']}: {c['text']}")
        lines.append(f"{c[id_field]}\t{text}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(chunks)


if __name__ == "__main__":
    n = build("policy_clauses.json", "id", "policy_clauses_chunked.tsv", ("clause_id", "text"))
    print(f"wrote graph/loading/policy_clauses_chunked.tsv ({n} rows)")
    n = build("typologies.json", "id", "typologies_chunked.tsv", ("typology_id", "description"))
    print(f"wrote graph/loading/typologies_chunked.tsv ({n} rows)")
