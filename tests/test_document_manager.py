import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from langchain_core.documents import Document

sys.path.insert(0, r"D:\nageoffer\agentic-rag-for-dummies\project")

from core.document_manager import DocumentManager  # noqa: E402


class FakeCollection:
    def __init__(self):
        self.added_batches = []

    def add_documents(self, documents):
        self.added_batches.append(list(documents))


class FakeVectorDb:
    def __init__(self, indexed_document_nos=None):
        self.indexed_document_nos = set(indexed_document_nos or [])
        self.create_calls = 0
        self.collection = FakeCollection()

    def create_collection(self, collection_name):
        self.create_calls += 1

    def get_collection(self, collection_name):
        return self.collection

    def get_indexed_document_nos(self):
        return set(self.indexed_document_nos)


class FakeParentStore:
    def __init__(self):
        self.saved_batches = []

    def save_many(self, parents):
        self.saved_batches.append(list(parents))


class FakeChunker:
    def create_chunks_single(self, md_path):
        source_name = f"{Path(md_path).stem}.pdf"
        parent_id = f"{Path(md_path).stem}_parent_0"
        parent_doc = Document(
            page_content="parent content",
            metadata={"source": source_name, "parent_id": parent_id},
        )
        child_doc = Document(
            page_content="child content",
            metadata={"source": source_name, "parent_id": parent_id, "chunk_id": f"{parent_id}_child_0"},
        )
        return [(parent_id, parent_doc)], [child_doc]


class FakeRagSystem:
    def __init__(self, indexed_document_nos=None):
        self.collection_name = "test_collection"
        self.vector_db = FakeVectorDb(indexed_document_nos=indexed_document_nos)
        self.parent_store = FakeParentStore()
        self.chunker = FakeChunker()


class DocumentManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="doc-manager-")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_markdown(self, filename: str, content: str = "# Title\n\ncontent"):
        path = Path(self.temp_dir) / filename
        path.write_text(content, encoding="utf-8")
        return path

    def test_index_existing_markdowns_skips_docs_already_in_database(self):
        rag_system = FakeRagSystem(indexed_document_nos={"already-indexed"})
        manager = DocumentManager(rag_system)
        manager.markdown_dir = Path(self.temp_dir)
        self._write_markdown("already-indexed.md")
        self._write_markdown("needs-index.md")

        result = manager.index_existing_markdowns(skip_existing=True)

        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(rag_system.vector_db.create_calls, 1)
        self.assertEqual(len(rag_system.parent_store.saved_batches), 1)
        self.assertEqual(len(rag_system.vector_db.collection.added_batches), 1)

    def test_local_document_stats_reflect_markdown_directory(self):
        rag_system = FakeRagSystem()
        manager = DocumentManager(rag_system)
        manager.markdown_dir = Path(self.temp_dir)
        self._write_markdown("alpha.md")
        self._write_markdown("beta.md")

        stats = manager.get_local_document_stats()

        self.assertEqual(stats["local_markdown_files"], 2)
        self.assertEqual(stats["local_markdown_names"], ["alpha.md", "beta.md"])

    def test_get_markdown_files_preserves_real_extension(self):
        rag_system = FakeRagSystem()
        manager = DocumentManager(rag_system)
        manager.markdown_dir = Path(self.temp_dir)
        self._write_markdown("care-plan.md")

        files = manager.get_markdown_files()

        self.assertEqual(files, ["care-plan.md"])

    def test_add_documents_with_report_explains_duplicate_markdown(self):
        rag_system = FakeRagSystem()
        manager = DocumentManager(rag_system)
        manager.markdown_dir = Path(self.temp_dir)
        existing = self._write_markdown("duplicate.md", "# Existing\n\nhello")
        duplicate_source_dir = Path(self.temp_dir) / "source"
        duplicate_source_dir.mkdir(parents=True, exist_ok=True)
        duplicate_source = duplicate_source_dir / "duplicate.md"
        duplicate_source.write_text("# Updated\n\nworld", encoding="utf-8")

        report = manager.add_documents_with_report([str(duplicate_source)])

        self.assertEqual(report["added"], 0)
        self.assertEqual(report["skipped"], 1)
        self.assertIn("同名 Markdown 已存在", report["skipped_details"][0])
        self.assertEqual(existing.read_text(encoding="utf-8"), "# Existing\n\nhello")


if __name__ == "__main__":
    unittest.main()
