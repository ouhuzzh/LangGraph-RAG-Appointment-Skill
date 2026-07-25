import argparse
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

import config  # noqa: E402
from api import jwt_utils  # noqa: E402
import kb_jobs  # noqa: E402


class JwtUtilsTests(unittest.TestCase):
    def test_token_pair_roundtrip(self):
        pair = jwt_utils.create_token_pair(user_id=42, username="alice", role="user")
        self.assertEqual(pair["token_type"], "bearer")

        access = jwt_utils.decode_token(pair["access_token"])
        self.assertIsNotNone(access)
        self.assertEqual(access["type"], "access")
        self.assertEqual(access["user_id"], 42)
        self.assertEqual(access["role"], "user")

        refresh = jwt_utils.decode_token(pair["refresh_token"])
        self.assertIsNotNone(refresh)
        self.assertEqual(refresh["type"], "refresh")

    def test_decode_garbage_returns_none(self):
        self.assertIsNone(jwt_utils.decode_token("not.a.jwt"))

    def test_decode_wrong_signature_returns_none(self):
        token = jwt_utils.create_access_token({"user_id": 1})
        with patch.object(config, "JWT_SECRET_KEY", "a-completely-different-secret"):
            self.assertIsNone(jwt_utils.decode_token(token))

    def test_expired_token_returns_none(self):
        with patch.object(config, "JWT_ACCESS_TOKEN_EXPIRE_MINUTES", -1):
            token = jwt_utils.create_access_token({"user_id": 1})
        self.assertIsNone(jwt_utils.decode_token(token))

    def test_token_issued_after_password_change_check(self):
        from datetime import datetime, timedelta, timezone
        token = jwt_utils.create_access_token({"user_id": 1})
        payload = jwt_utils.decode_token(token)
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        self.assertTrue(jwt_utils.token_issued_after(payload, past))
        self.assertFalse(jwt_utils.token_issued_after(payload, future))

    def test_legacy_token_without_iat_allowed(self):
        from datetime import datetime, timezone
        self.assertTrue(jwt_utils.token_issued_after({}, datetime.now(timezone.utc)))


class KbJobsWiringTests(unittest.TestCase):
    """Regression tests: kb_jobs sync entrypoints must attach the DocumentManager
    to the RAGSystem — the official-source sync path resolves it via
    ``rag_system.document_manager`` and crashed with AttributeError when unset."""

    def _fake_result(self):
        result = MagicMock()
        result.to_event.return_value = {}
        result.status = "completed"
        return result

    def test_sync_official_wires_document_manager(self):
        fake_rag = MagicMock()
        fake_dm = MagicMock()
        fake_dm.sync_official_source.return_value = self._fake_result()
        args = argparse.Namespace(source="medlineplus", limit=1)
        with patch.object(kb_jobs, "RAGSystem", return_value=fake_rag), \
             patch.object(kb_jobs, "DocumentManager", return_value=fake_dm), \
             patch.object(kb_jobs, "_print_json"):
            rc = kb_jobs._sync_official(args)
        self.assertEqual(rc, 0)
        self.assertIs(fake_rag.document_manager, fake_dm)
        fake_dm.sync_official_source.assert_called_once()

    def test_sync_local_wires_document_manager(self):
        fake_rag = MagicMock()
        fake_dm = MagicMock()
        fake_dm.sync_local_documents.return_value = self._fake_result()
        args = argparse.Namespace(soft_delete_missing=False)
        with patch.object(kb_jobs, "RAGSystem", return_value=fake_rag), \
             patch.object(kb_jobs, "DocumentManager", return_value=fake_dm), \
             patch.object(kb_jobs, "_print_json"):
            rc = kb_jobs._sync_local(args)
        self.assertEqual(rc, 0)
        self.assertIs(fake_rag.document_manager, fake_dm)
        fake_dm.sync_local_documents.assert_called_once()


if __name__ == "__main__":
    unittest.main()
