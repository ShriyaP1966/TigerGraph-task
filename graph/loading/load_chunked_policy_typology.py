"""Loads graph/loading/{policy_clauses,typologies}_chunked.tsv (POL-*/TYP-*,
built by build_chunked_policy_typology_tsv.py from P3's real chunked docs) into
the live TigerGraph instance, reusing the existing load_policy_typology_action
job. Additive only: these IDs are a different namespace from the existing
R1-R10 / pattern-name PolicyClause and FraudTypology vertices, so nothing
existing is touched or deleted.

Header rows are stripped before upload per pyTigerGraph's own documented
warning that USING header="true" isn't reliably honored through
runLoadingJobWithFile.

Usage: python graph/loading/load_chunked_policy_typology.py
"""
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from graph.mcp import tools as mcp_tools  # noqa: E402
from graph.mcp import config  # noqa: E402


def strip_header(src_path: Path) -> str:
    lines = src_path.read_text(encoding="utf-8").splitlines(keepends=True)
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=src_path.suffix, delete=False, encoding="utf-8", newline="")
    tmp.writelines(lines[1:])
    tmp.close()
    return tmp.name


def main():
    print(f"Connecting to TigerGraph (graph={config.TG_GRAPH})...")
    conn = mcp_tools._get_connection()
    print("Connected.\n")

    files = [
        (REPO_ROOT / "graph" / "loading" / "policy_clauses_chunked.tsv", "policy_file"),
        (REPO_ROOT / "graph" / "loading" / "typologies_chunked.tsv", "typology_file"),
    ]
    for src, tag in files:
        stripped = strip_header(src)
        print(f"Loading {src.name} as {tag} ...")
        result = conn.runLoadingJobWithFile(stripped, tag, "load_policy_typology_action", sep="\t")
        print(f"  -> {result}")

    print("\n=== Post-load counts ===")
    for v in ["PolicyClause", "FraudTypology", "Action", "ClosedCase"]:
        print(f"{v}: {conn.getVertexCount(v)}")

    print("\n=== get_policy_context('card_testing') sample ===")
    try:
        result = conn.runInstalledQuery("get_policy_context", params={"topic": "card_testing"})
        print(result)
    except Exception as e:
        print(f"query failed: {e}")


if __name__ == "__main__":
    main()
