"""Re-embed knowledge-base chunks with the CURRENT embedding model.

Symptom this repairs: a document was ingested with a different (or mock/placeholder)
embedding model, so its stored vectors are near-orthogonal to a semantically identical
query (cosine ~0). Semantic retrieval then never surfaces the document even though its
text is a perfect match, and the answer falls back to the "no evidence" disclaimer.

This recomputes ``child_chunks.embedding`` in place with the live model
(``model_factory.get_embedding_model``). Runs read-only by default; pass --apply to write.

Usage:
    python scripts/reembed_knowledge_base.py                 # dry-run report
    python scripts/reembed_knowledge_base.py --apply         # re-embed real docs
    python scripts/reembed_knowledge_base.py --apply --include-test-docs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from db.connection import connect  # noqa: E402
from db.vector_db_manager import _vector_literal  # noqa: E402
from model_factory import get_embedding_model  # noqa: E402

# Titles matching this prefix are stress-test / load-test artifacts, not real KB docs.
TEST_DOC_PREFIX = "live-doc-"
BATCH = 64


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the recomputed embeddings back to the database.")
    parser.add_argument(
        "--include-test-docs",
        action="store_true",
        help=f"Also re-embed chunks from '{TEST_DOC_PREFIX}*' test documents (skipped by default).",
    )
    parser.add_argument("--probe", default="高血压患者饮食生活方式注意事项", help="A query used to report a sanity score after re-embedding.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    conn = connect()
    cur = conn.cursor()
    emb = get_embedding_model()

    where = "" if args.include_test_docs else f"WHERE d.title NOT LIKE '{TEST_DOC_PREFIX}%%'"
    cur.execute(
        f"SELECT c.id, c.content FROM child_chunks c JOIN documents d ON d.id=c.document_id {where} ORDER BY c.id"
    )
    rows = cur.fetchall()
    print(f"child_chunks to re-embed: {len(rows)} (include_test_docs={args.include_test_docs})")
    if not rows:
        return 0

    if not args.apply:
        print("DRY-RUN: pass --apply to recompute and write embeddings.")
        return 0

    ids = [r[0] for r in rows]
    texts = [r[1] for r in rows]
    updated = 0
    for start in range(0, len(rows), BATCH):
        batch_ids = ids[start:start + BATCH]
        vecs = emb.embed_documents(texts[start:start + BATCH])
        for cid, vec in zip(batch_ids, vecs):
            cur.execute(
                "UPDATE child_chunks SET embedding = CAST(%s AS vector) WHERE id=%s",
                [_vector_literal(vec), cid],
            )
            updated += 1
        conn.commit()
        print(f"  re-embedded {updated}/{len(rows)}")

    # Sanity probe: top scores for the probe query should now be meaningfully > 0.
    v = _vector_literal(emb.embed_query(args.probe))
    cur.execute(
        "SELECT d.title, 1-(c.embedding <=> CAST(%s AS vector)) AS score "
        "FROM child_chunks c JOIN documents d ON d.id=c.document_id "
        "ORDER BY score DESC NULLS LAST LIMIT 5",
        [v],
    )
    print(f"top matches for probe {args.probe!r}:")
    for title, score in cur.fetchall():
        print(f"  {str(title)[:28]:28s} score={round(float(score), 3)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
