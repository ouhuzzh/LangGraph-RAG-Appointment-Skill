import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

import config  # noqa: E402
from db.semantic_cache_store import SemanticCacheStore, is_cacheable_turn  # noqa: E402


class _FakeEmbeddings:
    def embed_query(self, text):
        return [0.1, 0.2, 0.3]


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None


class _FakeConn:
    def __init__(self, rows):
        self._rows = list(rows)
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return _FakeCursor(self._rows)

    def commit(self):
        self.commits += 1


def _enable_cache(test_case):
    original = getattr(config, "ENABLE_SEMANTIC_CACHE", False)
    config.ENABLE_SEMANTIC_CACHE = True
    test_case.addCleanup(setattr, config, "ENABLE_SEMANTIC_CACHE", original)


class IsCacheableTurnTests(unittest.TestCase):
    def test_standalone_question_is_cacheable(self):
        self.assertTrue(is_cacheable_turn("高血压怎么控制饮食", {}))

    def test_too_short_query_rejected(self):
        self.assertFalse(is_cacheable_turn("头疼", {}))

    def test_pending_action_rejected(self):
        self.assertFalse(is_cacheable_turn("高血压怎么控制饮食", {"pending_action_type": "appointment"}))

    def test_pending_clarification_rejected(self):
        self.assertFalse(is_cacheable_turn("高血压怎么控制饮食", {"pending_clarification": "哪个科?"}))

    def test_followup_marker_rejected(self):
        # Context-dependent follow-up must never be cached.
        self.assertFalse(is_cacheable_turn("这个严重吗需要住院吗", {}))


class SelectHitTests(unittest.TestCase):
    def test_above_threshold_returns_payload(self):
        self.assertEqual(SemanticCacheStore._select_hit((7, "答案", 0.97), 0.95), (7, "答案"))

    def test_below_threshold_returns_none(self):
        self.assertIsNone(SemanticCacheStore._select_hit((7, "答案", 0.90), 0.95))

    def test_none_row_returns_none(self):
        self.assertIsNone(SemanticCacheStore._select_hit(None, 0.95))

    def test_malformed_row_returns_none(self):
        self.assertIsNone(SemanticCacheStore._select_hit((7, "答案", "abc"), 0.95))

    def test_nan_score_is_not_a_hit(self):
        # A NaN cosine score must never be served (nan < threshold is False).
        self.assertIsNone(SemanticCacheStore._select_hit((7, "答案", float("nan")), 0.95))


class LookupStoreTests(unittest.TestCase):
    def test_lookup_disabled_is_noop(self):
        # Flag off (default): must return None without embedding or DB access.
        config.ENABLE_SEMANTIC_CACHE = False
        boom = SemanticCacheStore(embeddings=_FakeEmbeddings())
        boom._connect = lambda: (_ for _ in ()).throw(AssertionError("must not connect"))
        self.assertIsNone(boom.lookup("高血压怎么控制饮食"))

    def test_lookup_returns_cached_answer_on_hit(self):
        _enable_cache(self)
        store = SemanticCacheStore(embeddings=_FakeEmbeddings())
        conn = _FakeConn([(1, "少盐、规律作息、遵医嘱服药。", 0.98)])
        store._connect = lambda: conn
        self.assertEqual(store.lookup("高血压怎么控制饮食"), "少盐、规律作息、遵医嘱服药。")
        self.assertEqual(conn.commits, 1)  # hit_count bump committed

    def test_lookup_miss_below_threshold(self):
        _enable_cache(self)
        store = SemanticCacheStore(embeddings=_FakeEmbeddings())
        store._connect = lambda: _FakeConn([(1, "无关答案", 0.70)])
        self.assertIsNone(store.lookup("高血压怎么控制饮食"))

    def test_lookup_fail_open_on_db_error(self):
        _enable_cache(self)
        store = SemanticCacheStore(embeddings=_FakeEmbeddings())
        store._connect = lambda: (_ for _ in ()).throw(RuntimeError("db down"))
        self.assertIsNone(store.lookup("高血压怎么控制饮食"))

    def test_store_inserts_when_no_duplicate(self):
        _enable_cache(self)
        store = SemanticCacheStore(embeddings=_FakeEmbeddings())
        conn = _FakeConn([])  # no existing near-duplicate
        store._connect = lambda: conn
        store.store("高血压怎么控制饮食", "少盐、规律作息、遵医嘱服药。")
        self.assertEqual(conn.commits, 1)

    def test_store_skips_when_duplicate_exists(self):
        _enable_cache(self)
        store = SemanticCacheStore(embeddings=_FakeEmbeddings())
        conn = _FakeConn([(1, "已有答案", 0.99)])  # near-duplicate already cached
        store._connect = lambda: conn
        store.store("高血压怎么控制饮食", "新答案")
        self.assertEqual(conn.commits, 0)  # no insert committed


if __name__ == "__main__":
    unittest.main()
