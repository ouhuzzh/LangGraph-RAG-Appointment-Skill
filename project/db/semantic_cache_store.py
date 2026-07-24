"""Semantic answer cache — reuse answers for highly similar past questions.

On a cache-eligible turn the incoming query is embedded and compared (pgvector
cosine) against previously answered queries.  A sufficiently similar, non-expired
entry short-circuits the whole agent graph and returns the stored answer.

Safety posture for a medical multi-turn assistant:
    - Off by default (``config.ENABLE_SEMANTIC_CACHE``).
    - ``is_cacheable_turn`` refuses context-dependent turns (pending action /
      clarification, follow-up pronouns, too-short queries) so a cached answer
      can never be served when the correct answer depends on dialogue context.
    - Every DB path is fail-open: any error degrades to a cache miss.
"""

from __future__ import annotations

import logging
import math

import config

logger = logging.getLogger(__name__)


# Strong context-dependence markers: if the query leans on prior dialogue, its
# answer is not safely cacheable across sessions.
_FOLLOWUP_MARKERS = (
    "那个", "这个", "那种", "这种", "它", "刚才", "上面", "前面",
    "之前", "继续", "接着", "还有呢", "上述", "刚说",
)


def is_cacheable_turn(query: str, session_state: dict | None) -> bool:
    """Whether this turn may be served from / written to the semantic cache."""
    q = (query or "").strip()
    if len(q) < int(getattr(config, "SEMANTIC_CACHE_MIN_QUERY_CHARS", 6)):
        return False
    state = session_state or {}
    if state.get("pending_action_type") or state.get("pending_clarification") or state.get("pending_candidates"):
        return False
    if any(marker in q for marker in _FOLLOWUP_MARKERS):
        return False
    return True


def _vector_literal(values) -> str:
    return "[" + ",".join(f"{float(v):.8f}" for v in values) + "]"


class SemanticCacheStore:
    """pgvector-backed cache of ``(query embedding) -> answer``."""

    def __init__(self, embeddings=None, *, embedding_factory=None):
        self._embeddings = embeddings
        self._embedding_factory = embedding_factory
        self._embeddings_resolved = embeddings is not None

    @property
    def enabled(self) -> bool:
        return bool(getattr(config, "ENABLE_SEMANTIC_CACHE", False))

    def _connect(self):
        from db.connection import connect
        return connect()

    def _get_embeddings(self):
        if self._embeddings_resolved:
            return self._embeddings
        self._embeddings_resolved = True
        factory = self._embedding_factory
        if factory is None:
            from model_factory import get_embedding_model
            factory = get_embedding_model
        self._embeddings = factory()
        return self._embeddings

    @staticmethod
    def _select_hit(row, threshold: float):
        """Pure decision: return ``(id, response)`` when the row clears the
        similarity threshold, else ``None``.  Kept side-effect free for tests."""
        if not row:
            return None
        try:
            score = float(row[2])
        except (TypeError, ValueError, IndexError):
            return None
        if not math.isfinite(score) or score < threshold:
            return None
        return (row[0], row[1])

    def lookup(self, query: str):
        """Return a cached answer for a highly similar past query, else ``None``.
        Never raises — any failure is treated as a cache miss."""
        if not self.enabled:
            return None
        q = (query or "").strip()
        if len(q) < int(getattr(config, "SEMANTIC_CACHE_MIN_QUERY_CHARS", 6)):
            return None
        threshold = float(getattr(config, "SEMANTIC_CACHE_SIMILARITY_THRESHOLD", 0.95))
        ttl = int(getattr(config, "SEMANTIC_CACHE_TTL_SECONDS", 604800))
        try:
            literal = _vector_literal(self._get_embeddings().embed_query(q))
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, response_text, 1 - (embedding <=> CAST(%s AS vector)) AS score
                        FROM semantic_cache
                        WHERE embedding IS NOT NULL
                          AND created_at >= NOW() - make_interval(secs => %s)
                        ORDER BY embedding <=> CAST(%s AS vector)
                        LIMIT 1
                        """,
                        (literal, ttl, literal),
                    )
                    row = cur.fetchone()
                hit = self._select_hit(row, threshold)
                if hit is None:
                    return None
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE semantic_cache SET hit_count = hit_count + 1, last_hit_at = NOW() WHERE id = %s",
                        (hit[0],),
                    )
                conn.commit()
                return hit[1]
        except Exception:
            logger.debug("Semantic cache lookup failed; treating as miss", exc_info=True)
            return None

    def store(self, query: str, response: str) -> None:
        """Persist ``query -> response``.  Skips when a near-duplicate already
        exists so the cache does not accumulate redundant rows.  Never raises."""
        if not self.enabled:
            return
        q = (query or "").strip()
        r = (response or "").strip()
        if len(q) < int(getattr(config, "SEMANTIC_CACHE_MIN_QUERY_CHARS", 6)) or not r:
            return
        threshold = float(getattr(config, "SEMANTIC_CACHE_SIMILARITY_THRESHOLD", 0.95))
        ttl = int(getattr(config, "SEMANTIC_CACHE_TTL_SECONDS", 604800))
        try:
            literal = _vector_literal(self._get_embeddings().embed_query(q))
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, response_text, 1 - (embedding <=> CAST(%s AS vector)) AS score
                        FROM semantic_cache
                        WHERE embedding IS NOT NULL
                          AND created_at >= NOW() - make_interval(secs => %s)
                        ORDER BY embedding <=> CAST(%s AS vector)
                        LIMIT 1
                        """,
                        (literal, ttl, literal),
                    )
                    if self._select_hit(cur.fetchone(), threshold) is not None:
                        return
                    cur.execute(
                        "INSERT INTO semantic_cache (query_text, response_text, embedding) "
                        "VALUES (%s, %s, CAST(%s AS vector))",
                        (q, r, literal),
                    )
                conn.commit()
        except Exception:
            logger.debug("Semantic cache store failed; skipping", exc_info=True)
