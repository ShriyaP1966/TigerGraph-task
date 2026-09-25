"""
Turns raw policy / fraud-typology / regulatory reference documents into clean,
stably-ID'd chunks.

Input:  docs/policy/raw/{policy,typology,regulatory}/*.md (or .txt)
        Each `##` heading starts a new chunk; everything until the next `##`
        (or end of file) is that chunk's text.

Output: docs/policy/chunks/{policy_clauses,typologies,regulatory_references}.json
        Each entry: {id, title, text, source_file}

Loaded as PolicyClause / FraudTypology graph vertices, and cited by ID in
agent explanations (e.g. "per POL-004").

IDs are kept stable across re-runs via docs/policy/chunks/_id_map.json,
keyed on (category, title) — so re-chunking after editing a doc does not
silently renumber clauses that other parts of the system already reference.

Usage:
    python scripts/chunk_policy_docs.py
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "docs" / "policy" / "raw"
CHUNKS_DIR = REPO_ROOT / "docs" / "policy" / "chunks"

CATEGORIES = {
    "policy": {"prefix": "POL", "raw_subdir": "policy", "out_file": "policy_clauses.json"},
    "typology": {"prefix": "TYP", "raw_subdir": "typology", "out_file": "typologies.json"},
    "regulatory": {"prefix": "REG", "raw_subdir": "regulatory", "out_file": "regulatory_references.json"},
}

HEADING_RE = re.compile(r"^##\s+(.*)$", re.MULTILINE)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def strip_comments(text: str) -> str:
    return HTML_COMMENT_RE.sub("", text).strip()


def split_into_sections(text: str):
    """Split markdown text on '##' headings. Returns list of (title, body)."""
    text = strip_comments(text)
    matches = list(HEADING_RE.finditer(text))
    sections = []
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((title, body))
    return sections


def load_id_map():
    path = CHUNKS_DIR / "_id_map.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_id_map(id_map):
    path = CHUNKS_DIR / "_id_map.json"
    path.write_text(json.dumps(id_map, indent=2, ensure_ascii=False), encoding="utf-8")


def next_id(id_map, category, prefix):
    used_numbers = {
        int(v.split("-")[1])
        for k, v in id_map.items()
        if k.startswith(f"{category}::")
    }
    n = 1
    while n in used_numbers:
        n += 1
    return f"{prefix}-{n:03d}"


def main():
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    id_map = load_id_map()

    total_chunks = 0
    for category, cfg in CATEGORIES.items():
        raw_subdir = RAW_DIR / cfg["raw_subdir"]
        source_files = sorted(list(raw_subdir.glob("*.md")) + list(raw_subdir.glob("*.txt")))

        chunks = []
        for f in source_files:
            text = f.read_text(encoding="utf-8")
            for title, body in split_into_sections(text):
                map_key = f"{category}::{title}"
                if map_key not in id_map:
                    id_map[map_key] = next_id(id_map, category, cfg["prefix"])
                chunks.append({
                    "id": id_map[map_key],
                    "title": title,
                    "text": body,
                    "source_file": f.name,
                    "is_sample_placeholder": f.name.startswith("SAMPLE_"),
                })

        chunks.sort(key=lambda c: c["id"])
        out_path = CHUNKS_DIR / cfg["out_file"]
        out_path.write_text(json.dumps(chunks, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{category}: {len(chunks)} chunk(s) from {len(source_files)} file(s) -> {out_path.relative_to(REPO_ROOT)}")
        total_chunks += len(chunks)

    save_id_map(id_map)

    sample_count = 0
    for cfg in CATEGORIES.values():
        data = json.loads((CHUNKS_DIR / cfg["out_file"]).read_text(encoding="utf-8"))
        sample_count += sum(1 for c in data if c["is_sample_placeholder"])

    print(f"\nTotal chunks written: {total_chunks}")
    if sample_count:
        print(
            f"WARNING: {sample_count} chunk(s) came from SAMPLE_* placeholder files. "
            "Replace docs/policy/raw/**/SAMPLE_* with the real dataset documents "
            "and re-run this script before final submission."
        )


if __name__ == "__main__":
    main()
