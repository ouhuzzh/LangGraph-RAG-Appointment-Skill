import sys
import unittest

sys.path.insert(0, r"D:\nageoffer\agentic-rag-for-dummies\project")

from core.chat_interface import ChatInterface  # noqa: E402


class FakeGraphState:
    next = False


class FakeGraph:
    def get_state(self, config):
        return FakeGraphState()


class FakeVectorDb:
    def __init__(self, has_documents=False):
        self._has_documents = has_documents

    def has_documents(self):
        return self._has_documents


class FakeMemory:
    def get_state(self, thread_id):
        return {}


class FakeRagSystem:
    def __init__(self):
        self.agent_graph = FakeGraph()
        self.thread_id = "thread-chat"
        self.session_memory = FakeMemory()
        self.vector_db = FakeVectorDb(has_documents=False)

    def get_config(self):
        return {}


class ChatInterfaceTests(unittest.TestCase):
    def test_chat_returns_friendly_message_when_knowledge_base_is_empty(self):
        interface = ChatInterface(FakeRagSystem())

        responses = list(interface.chat("高血压是什么", []))

        self.assertEqual(len(responses), 1)
        self.assertIn("知识库里还没有可检索文档", responses[0])

    def test_infer_intent_does_not_let_pending_appointment_hijack_unrelated_medical_question(self):
        intent = ChatInterface._infer_intent(
            "高血压会引起头晕吗",
            {"pending_action_type": "appointment", "pending_action_payload": {"department": "呼吸内科"}},
        )

        self.assertEqual(intent, "medical_rag")

    def test_infer_intent_keeps_pending_appointment_for_short_acknowledgement(self):
        intent = ChatInterface._infer_intent(
            "可以",
            {"pending_action_type": "appointment", "pending_action_payload": {"department": "呼吸内科"}},
        )

        self.assertEqual(intent, "appointment")

    def test_infer_intent_keeps_pending_clarification_for_schedule_answer(self):
        intent = ChatInterface._infer_intent(
            "明天下午",
            {"intent": "appointment", "pending_clarification": "请补充时间"},
        )

        self.assertEqual(intent, "appointment")


if __name__ == "__main__":
    unittest.main()
