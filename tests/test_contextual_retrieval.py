import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

import config  # noqa: E402
from core.contextual_enricher import ContextualChunkEnricher  # noqa: E402
from core.document_chunker import DocumentChuncker  # noqa: E402
from db.vector_db_manager import _build_embedding_text  # noqa: E402
from langchain_core.documents import Document  # noqa: E402


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    """Minimal stand-in mirroring the with_config/bind/invoke chain used in prod."""

    def __init__(self, content="这是关于高血压一线用药剂量的章节定位说明。"):
        self._content = content
        self.calls = 0

    def with_config(self, **kwargs):
        return self

    def bind(self, **kwargs):
        return self

    def invoke(self, messages):
        self.calls += 1
        return _FakeResp(self._content)


class _BoomLLMFactory:
    def __call__(self):
        raise RuntimeError("model provider unavailable")


def _enable_contextual_retrieval(test_case):
    original = getattr(config, "ENABLE_CONTEXTUAL_RETRIEVAL", False)
    config.ENABLE_CONTEXTUAL_RETRIEVAL = True
    test_case.addCleanup(setattr, config, "ENABLE_CONTEXTUAL_RETRIEVAL", original)


class BuildEmbeddingTextTests(unittest.TestCase):
    def test_prepends_contextual_summary_when_present(self):
        doc = Document(
            page_content="收缩压持续升高需要评估靶器官损害。",
            metadata={"contextual_summary": "本块讲高血压的靶器官评估", "section_title": "并发症"},
        )
        text = _build_embedding_text(doc)
        self.assertTrue(text.startswith("context: 本块讲高血压的靶器官评估"))
        self.assertIn("section_title: 并发症", text)
        self.assertTrue(text.endswith("收缩压持续升高需要评估靶器官损害。"))

    def test_no_summary_leaves_legacy_behavior(self):
        doc = Document(
            page_content="正文内容。",
            metadata={"section_title": "定义"},
        )
        text = _build_embedding_text(doc)
        self.assertNotIn("context:", text)
        self.assertTrue(text.startswith("section_title: 定义"))


class ContextualChunkEnricherTests(unittest.TestCase):
    def _child(self):
        return Document(
            page_content="一线降压药包括 ACEI 与 ARB。",
            metadata={"parent_id": "doc_parent_0", "section_title": "药物治疗", "document_topic": "高血压"},
        )

    def test_sets_summary_with_llm(self):
        _enable_contextual_retrieval(self)
        llm = _FakeLLM()
        enricher = ContextualChunkEnricher(llm=llm)
        child = self._child()
        enricher.enrich_child_chunks([child], parent_lookup={"doc_parent_0": "高血压药物治疗章节全文……"})
        self.assertEqual(child.metadata["contextual_summary"], "这是关于高血压一线用药剂量的章节定位说明。")
        self.assertEqual(llm.calls, 1)

    def test_noop_when_disabled(self):
        # Flag left at its default (False) — enricher must not call the LLM.
        config.ENABLE_CONTEXTUAL_RETRIEVAL = False
        self.addCleanup(setattr, config, "ENABLE_CONTEXTUAL_RETRIEVAL",
                        getattr(config, "ENABLE_CONTEXTUAL_RETRIEVAL", False))
        llm = _FakeLLM()
        child = self._child()
        ContextualChunkEnricher(llm=llm).enrich_child_chunks([child])
        self.assertNotIn("contextual_summary", child.metadata)
        self.assertEqual(llm.calls, 0)

    def test_never_raises_when_llm_init_fails(self):
        _enable_contextual_retrieval(self)
        enricher = ContextualChunkEnricher(chat_model_factory=_BoomLLMFactory())
        child = self._child()
        # Must degrade to a no-op instead of propagating the provider error.
        enricher.enrich_child_chunks([child])
        self.assertNotIn("contextual_summary", child.metadata)

    def test_skips_already_enriched_chunk(self):
        _enable_contextual_retrieval(self)
        llm = _FakeLLM()
        child = self._child()
        child.metadata["contextual_summary"] = "已有摘要"
        ContextualChunkEnricher(llm=llm).enrich_child_chunks([child])
        self.assertEqual(child.metadata["contextual_summary"], "已有摘要")
        self.assertEqual(llm.calls, 0)


class ChunkerEnrichmentIntegrationTests(unittest.TestCase):
    def test_chunker_enriches_children_end_to_end(self):
        _enable_contextual_retrieval(self)
        markdown = (
            "Source: World Health Organization\n"
            "Source type: public_health\n"
            "Title: Hypertension\n\n"
            "# Hypertension\n\n"
        ) + ("血压监测非常重要，需要长期坚持。\n" * 250)

        with tempfile.TemporaryDirectory(prefix="ctx-enrich-") as temp_dir:
            md_path = Path(temp_dir) / "who-hypertension.md"
            md_path.write_text(markdown, encoding="utf-8")
            chunker = DocumentChuncker(enricher=ContextualChunkEnricher(llm=_FakeLLM("定位说明")))
            _, child_chunks = chunker.create_chunks_single(md_path)

        self.assertTrue(child_chunks)
        self.assertEqual(child_chunks[0].metadata["contextual_summary"], "定位说明")
        self.assertTrue(_build_embedding_text(child_chunks[0]).startswith("context: 定位说明"))

    def test_chunker_without_enricher_is_unchanged(self):
        markdown = (
            "Title: Cold\n\n# Cold\n\n"
        ) + ("多喝水，注意休息。\n" * 250)
        with tempfile.TemporaryDirectory(prefix="ctx-plain-") as temp_dir:
            md_path = Path(temp_dir) / "cold.md"
            md_path.write_text(markdown, encoding="utf-8")
            _, child_chunks = DocumentChuncker().create_chunks_single(md_path)
        self.assertTrue(child_chunks)
        self.assertNotIn("contextual_summary", child_chunks[0].metadata)


if __name__ == "__main__":
    unittest.main()
