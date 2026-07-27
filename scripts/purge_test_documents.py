"""Purge stress-test / load-test documents left in the knowledge base.

Load and stress tests ingest throwaway documents titled ``live-doc-<hex>`` that
pollute retrieval (an irrelevant junk chunk can occupy a top-k slot). This removes
those documents and their parent/child chunks. Real KB documents are untouched.

Read-only by default; pass --apply to delete.

Usage:
    python scripts/purge_test_documents.py            # dry-run report
    python scripts/purge_test_documents.py --apply    # delete the test docs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from db.connection import connect  # noqa: E402

TEST_DOC_PREFIX = "live-doc-"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Delete the test documents (otherwise dry-run).")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    conn = connect()
    cur = conn.cursor()

    cur.execute("SELECT id FROM documents WHERE title LIKE %s", [f"{TEST_DOC_PREFIX}%"])
    doc_ids = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT count(*) FROM documents")
    total_docs = cur.fetchone()[0]

    def chunk_count(table: str) -> int:
        if not doc_ids:
            return 0
        cur.execute(f"SELECT count(*) FROM {table} WHERE document_id = ANY(%s)", [doc_ids])
        return cur.fetchone()[0]

    child_n = chunk_count("child_chunks")
    parent_n = chunk_count("parent_chunks")
    print(f"test documents: {len(doc_ids)} / {total_docs} total")
    print(f"  child_chunks to delete:  {child_n}")
    print(f"  parent_chunks to delete: {parent_n}")

    if not doc_ids:
        print("nothing to purge.")
        return 0
    if not args.apply:
        print("DRY-RUN: pass --apply to delete.")
        return 0

    # Delete children first (FK safety), then parents, then the documents.
    cur.execute("DELETE FROM child_chunks WHERE document_id = ANY(%s)", [doc_ids])
    cur.execute("DELETE FROM parent_chunks WHERE document_id = ANY(%s)", [doc_ids])
    cur.execute("DELETE FROM documents WHERE id = ANY(%s)", [doc_ids])
    conn.commit()

    cur.execute("SELECT count(*) FROM child_chunks")
    remaining_children = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM documents")
    remaining_docs = cur.fetchone()[0]
    print(f"purged. remaining documents={remaining_docs} child_chunks={remaining_children}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
