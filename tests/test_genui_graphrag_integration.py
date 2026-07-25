"""Integration tests for GraphRAG retrieval path + Generative UI card detection."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

import config  # noqa: E402
from api.sse import _detect_card_events  # noqa: E402


class DetectCardEventsTests(unittest.TestCase):
    """Test the heuristic-based structured UI card detection from answer text."""

    def test_department_recommendation_emits_card(self):
        text = "建议优先咨询 **心内科**。\n\n原因：胸痛是心血管问题的常见症状。"
        events = _detect_card_events(text, "thread-1")
        self.assertEqual(len(events), 1)
        self.assertIn("department", events[0])
        self.assertIn("心内科", events[0])

    def test_emergency_alert_emits_risk_card(self):
        text = "⚠️ **紧急提醒**\n\n你描述的症状包含需要立即处理的危险信号。请立刻拨打 120。"
        events = _detect_card_events(text, "thread-2")
        self.assertEqual(len(events), 1)
        self.assertIn("risk_alert", events[0])
        self.assertIn("critical", events[0])

    def test_high_risk_alert_emits_card(self):
        text = "⚠️ **风险提醒**\n\n你描述的症状风险较高。"
        events = _detect_card_events(text, "thread-3")
        self.assertEqual(len(events), 1)
        self.assertIn("risk_alert", events[0])
        self.assertIn("high", events[0])

    def test_appointment_preview_emits_card(self):
        text = "以下是预约预览，请确认预约。\n张医生 2026-04-18 下午"
        events = _detect_card_events(text, "thread-4")
        self.assertEqual(len(events), 1)
        self.assertIn("appointment_preview", events[0])

    def test_plain_medical_answer_emits_no_card(self):
        text = "高血压是常见的慢性病，需要长期管理。建议少盐饮食、规律运动。"
        events = _detect_card_events(text, "thread-5")
        self.assertEqual(len(events), 0)

    def test_empty_content_emits_no_card(self):
        self.assertEqual(_detect_card_events("", "t"), [])


class GraphRAGRetrievalIntegrationTests(unittest.TestCase):
    """Test GraphRAG entity extraction + hop query integration (mocked DB)."""

    def test_extract_entities_finds_medical_terms(self):
        from db.knowledge_graph_store import KnowledgeGraphStore
        entities = KnowledgeGraphStore.extract_query_entities("高血压吃什么降压药最好")
        self.assertIn("高血压", entities)
        self.assertIn("降压药", entities)

    def test_graph_hop_disabled_returns_empty(self):
        from db.knowledge_graph_store import KnowledgeGraphStore
        config.ENABLE_GRAPH_RAG = False
        self.addCleanup(setattr, config, "ENABLE_GRAPH_RAG", False)
        store = KnowledgeGraphStore()
        result = store.graph_hop_query(["高血压"])
        self.assertEqual(result, set())

    def test_graph_hop_empty_terms_returns_empty(self):
        from db.knowledge_graph_store import KnowledgeGraphStore
        original = getattr(config, "ENABLE_GRAPH_RAG", False)
        config.ENABLE_GRAPH_RAG = True
        self.addCleanup(setattr, config, "ENABLE_GRAPH_RAG", original)
        store = KnowledgeGraphStore()
        result = store.graph_hop_query([])
        self.assertEqual(result, set())


if __name__ == "__main__":
    unittest.main()
