import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

import config  # noqa: E402
from core.knowledge_graph_extractor import (  # noqa: E402
    KnowledgeGraphExtractor,
    Triple,
    parse_triples_json,
)
from db.knowledge_graph_store import KnowledgeGraphStore  # noqa: E402


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    def __init__(self, content=""):
        self._content = content
        self.calls = 0

    def with_config(self, **kwargs):
        return self

    def bind(self, **kwargs):
        return self

    def invoke(self, messages):
        self.calls += 1
        return _FakeResp(self._content)


def _enable_graph_rag(test_case):
    original = getattr(config, "ENABLE_GRAPH_RAG", False)
    config.ENABLE_GRAPH_RAG = True
    test_case.addCleanup(setattr, config, "ENABLE_GRAPH_RAG", original)


_SAMPLE_LLM_OUTPUT = """```json
[
  {"subject": "高血压", "subject_type": "disease", "relation": "has_symptom", "object": "头痛", "object_type": "symptom"},
  {"subject": "高血压", "subject_type": "disease", "relation": "belongs_to", "object": "心内科", "object_type": "department"},
  {"subject": "ACEI", "subject_type": "drug", "relation": "treats", "object": "高血压", "object_type": "disease"}
]
```"""


class ParseTriplesJsonTests(unittest.TestCase):
    def test_valid_json_produces_triples(self):
        triples = parse_triples_json(_SAMPLE_LLM_OUTPUT, source_parent_id="p1")
        self.assertEqual(len(triples), 3)
        self.assertEqual(triples[0].subject, "高血压")
        self.assertEqual(triples[0].relation, "has_symptom")
        self.assertEqual(triples[0].object, "头痛")
        self.assertEqual(triples[0].source_parent_id, "p1")

    def test_invalid_json_returns_empty(self):
        self.assertEqual(parse_triples_json("not json at all"), [])

    def test_unknown_entity_type_filtered(self):
        raw = '[{"subject": "foo", "subject_type": "planet", "relation": "treats", "object": "bar", "object_type": "drug"}]'
        self.assertEqual(parse_triples_json(raw), [])

    def test_unknown_relation_filtered(self):
        raw = '[{"subject": "A", "subject_type": "drug", "relation": "loves", "object": "B", "object_type": "disease"}]'
        self.assertEqual(parse_triples_json(raw), [])

    def test_empty_fields_skipped(self):
        raw = '[{"subject": "", "subject_type": "drug", "relation": "treats", "object": "B", "object_type": "disease"}]'
        self.assertEqual(parse_triples_json(raw), [])


class KnowledgeGraphExtractorTests(unittest.TestCase):
    def test_extracts_triples_with_fake_llm(self):
        _enable_graph_rag(self)
        extractor = KnowledgeGraphExtractor(llm=_FakeLLM(_SAMPLE_LLM_OUTPUT))
        triples = extractor.extract_from_parent("p1", "高血压是常见慢性病...")
        self.assertEqual(len(triples), 3)

    def test_noop_when_disabled(self):
        config.ENABLE_GRAPH_RAG = False
        self.addCleanup(setattr, config, "ENABLE_GRAPH_RAG", False)
        llm = _FakeLLM(_SAMPLE_LLM_OUTPUT)
        extractor = KnowledgeGraphExtractor(llm=llm)
        self.assertEqual(extractor.extract_from_parent("p1", "text"), [])
        self.assertEqual(llm.calls, 0)

    def test_never_raises_on_llm_failure(self):
        _enable_graph_rag(self)
        extractor = KnowledgeGraphExtractor(chat_model_factory=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        result = extractor.extract_from_parent("p1", "text")
        self.assertEqual(result, [])


class ExtractQueryEntitiesTests(unittest.TestCase):
    def test_extracts_chinese_medical_terms(self):
        entities = KnowledgeGraphStore.extract_query_entities("高血压应该吃什么药")
        self.assertIn("高血压", entities)

    def test_filters_stopwords(self):
        entities = KnowledgeGraphStore.extract_query_entities("什么是高血压")
        self.assertNotIn("什么", entities)
        self.assertIn("高血压", entities)

    def test_empty_query(self):
        self.assertEqual(KnowledgeGraphStore.extract_query_entities(""), [])

    def test_english_terms(self):
        entities = KnowledgeGraphStore.extract_query_entities("what is hypertension treatment?")
        self.assertIn("hypertension", entities)
        self.assertIn("treatment", entities)


if __name__ == "__main__":
    unittest.main()
