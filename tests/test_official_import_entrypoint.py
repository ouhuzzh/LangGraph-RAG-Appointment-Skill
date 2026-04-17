import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, r"D:\nageoffer\agentic-rag-for-dummies\project")

from core.document_manager import DocumentManager  # noqa: E402


class FakeRagSystem:
    def __init__(self):
        self.collection_name = "test"
        self.refreshed = False

    def refresh_knowledge_base_status(self):
        self.refreshed = True


class OfficialImportEntrypointTests(unittest.TestCase):
    def test_import_official_source_calls_importer_and_indexing(self):
        rag_system = FakeRagSystem()
        manager = DocumentManager(rag_system)
        manager.markdown_dir = Path(r"D:\nageoffer\agentic-rag-for-dummies\markdown_docs")

        fake_result = mock.Mock(downloaded=3, written=2, skipped=1, failed=0, discovered_url="manifest")
        with mock.patch("core.document_manager.MedlinePlusXmlImporter") as importer_cls:
            importer_cls.return_value.import_latest.return_value = fake_result
            with mock.patch.object(manager, "index_existing_markdowns", return_value={"processed": 2, "added": 2, "skipped": 0}) as index_mock:
                result, index_result = manager.import_official_source("medlineplus", limit=3, overwrite=False, index_after_import=True)

        self.assertEqual(result, fake_result)
        self.assertEqual(index_result["added"], 2)
        importer_cls.return_value.import_latest.assert_called_once()
        index_mock.assert_called_once()
        self.assertTrue(rag_system.refreshed)


if __name__ == "__main__":
    unittest.main()
