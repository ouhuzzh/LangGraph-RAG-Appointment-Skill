"""Knowledge Graph Store — persist and query medical knowledge triples.

Stores (subject, relation, object) triples extracted from document chunks in
PostgreSQL.  Supports multi-hop graph traversal queries that return related
parent_ids, which are then converted to retrieval results and fused via RRF
into the main search pipeline.

Gated by ``config.ENABLE_GRAPH_RAG`` (off by default).  All DB paths are
fail-open: errors degrade to empty results, never breaking retrieval.
"""

from __future__ import annotations

import logging
from typing import List, Set

import config

logger = logging.getLogger(__name__)


class KnowledgeGraphStore:
    """pgvector-backed store for medical knowledge graph triples."""

    def __init__(self):
        pass

    @property
    def enabled(self) -> bool:
        return bool(getattr(config, "ENABLE_GRAPH_RAG", False))

    def _connect(self):
        from db.connection import connect
        return connect()

    def save_triples(self, triples) -> int:
        """Bulk-insert triples. Returns count of inserted rows. Never raises."""
        if not self.enabled or not triples:
            return 0
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    inserted = 0
                    for t in triples:
                        cur.execute(
                            """
                            INSERT INTO kg_triples (subject, subject_type, relation, object, object_type,
                                                   source_parent_id, source_document_no)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (t.subject, t.subject_type, t.relation, t.object, t.object_type,
                             t.source_parent_id, t.source_document_no),
                        )
                        inserted += cur.rowcount
                conn.commit()
                return inserted
        except Exception:
            logger.debug("KnowledgeGraphStore: save_triples failed", exc_info=True)
            return 0

    def graph_hop_query(self, entity_terms: List[str], *, max_hops: int = 2) -> Set[str]:
        """Multi-hop traversal: find parent_ids reachable from entity terms.

        Starting from entities matching any of ``entity_terms`` (as subject OR
        object), follow relations up to ``max_hops`` times, collecting all
        encountered ``source_parent_id`` values.

        Returns a set of parent_ids that can be used to retrieve chunks from
        the main vector store.  Never raises.
        """
        if not self.enabled or not entity_terms:
            return set()
        try:
            terms = [t.strip().lower() for t in entity_terms if t.strip()]
            if not terms:
                return set()
            max_hops = min(max_hops, int(getattr(config, "GRAPH_RAG_MAX_HOPS", 2)))
            with self._connect() as conn:
                with conn.cursor() as cur:
                    # Seed: find entities matching the query terms
                    placeholders = ",".join(["%s"] * len(terms))
                    cur.execute(
                        f"""
                        SELECT DISTINCT source_parent_id, subject, object
                        FROM kg_triples
                        WHERE LOWER(subject) = ANY(ARRAY[{placeholders}])
                           OR LOWER(object) = ANY(ARRAY[{placeholders}])
                        LIMIT 50
                        """,
                        (*terms, *terms),
                    )
                    rows = cur.fetchall()
                    parent_ids: Set[str] = set()
                    frontier: Set[str] = set()
                    for row in rows:
                        if row[0]:
                            parent_ids.add(row[0])
                        frontier.add(row[1].lower() if row[1] else "")
                        frontier.add(row[2].lower() if row[2] else "")
                    frontier -= {""}
                    visited = set(terms) | frontier

                    # Multi-hop expansion
                    for _ in range(max_hops - 1):
                        if not frontier:
                            break
                        hop_terms = list(frontier)[:20]
                        hop_placeholders = ",".join(["%s"] * len(hop_terms))
                        cur.execute(
                            f"""
                            SELECT DISTINCT source_parent_id, subject, object
                            FROM kg_triples
                            WHERE LOWER(subject) = ANY(ARRAY[{hop_placeholders}])
                               OR LOWER(object) = ANY(ARRAY[{hop_placeholders}])
                            LIMIT 100
                            """,
                            (*hop_terms, *hop_terms),
                        )
                        hop_rows = cur.fetchall()
                        new_frontier: Set[str] = set()
                        for row in hop_rows:
                            if row[0]:
                                parent_ids.add(row[0])
                            for entity in (row[1], row[2]):
                                e = (entity or "").strip().lower()
                                if e and e not in visited:
                                    new_frontier.add(e)
                        visited |= new_frontier
                        frontier = new_frontier

            return parent_ids
        except Exception:
            logger.debug("KnowledgeGraphStore: graph_hop_query failed", exc_info=True)
            return set()

    @staticmethod
    def extract_query_entities(query: str) -> List[str]:
        """Heuristic entity extraction from a user query.

        Generates 2-4 char Chinese n-grams from contiguous runs (captures
        multi-char medical terms like 高血压, 糖尿病 regardless of position)
        and English words >= 3 chars.  Prioritizes 3-char terms (the most common
        medical term length in Chinese).  Pure function for testing.
        """
        import re
        text = (query or "").strip()
        if not text:
            return []
        stopwords = {"什么", "怎么", "如何", "一下", "请问", "这个", "那个", "可以",
                     "应该", "需要", "现在", "一般", "情况", "问题", "the", "and", "for"}
        # Chinese: generate 2-4 char n-grams from contiguous runs
        cn_runs = re.findall(r"[\u4e00-\u9fff]+", text)
        cn_terms: set = set()
        for run in cn_runs:
            for n in range(2, 5):
                for i in range(len(run) - n + 1):
                    cn_terms.add(run[i:i + n])
        # English: extract 3+ char words
        en_terms = set(re.findall(r"[a-zA-Z]{3,}", text.lower()))
        # Combine, filter stopwords, prioritize 3-char terms (typical medical term length)
        all_terms = (cn_terms | en_terms) - stopwords

        def _priority(t):
            length = len(t)
            return (0 if length == 3 else (1 if length == 2 else 2), t)

        return sorted(all_terms, key=_priority)[:10]
