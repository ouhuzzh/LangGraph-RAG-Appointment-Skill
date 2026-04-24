import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from api.app import create_app  # noqa: E402
from api.dependencies import set_container_for_tests  # noqa: E402


class FakeSessionMemory:
    def __init__(self):
        self.cleared = []

    def get_recent_messages(self, thread_id):
        return [
            HumanMessage(content="你好"),
            AIMessage(content=f"你好，我记得当前会话是 {thread_id}"),
        ]


class FakeRagSystem:
    def __init__(self):
        self.session_memory = FakeSessionMemory()
        self.cleared = []

    def get_system_status(self):
        return {
            "state": "ready",
            "message": "系统已就绪。",
            "last_error": "",
            "steps": {"graph_compile": {"state": "completed"}},
        }

    def get_knowledge_base_status(self):
        return {
            "status": "ready",
            "message": "知识库可检索。",
            "last_error": "",
            "stats": {"documents": 2, "child_chunks": 12},
        }

    def reset_thread(self, thread_id=None):
        self.cleared.append(thread_id)


class FakeChatInterface:
    def __init__(self, rag_system):
        self.rag_system = rag_system
        self.calls = []

    def chat(self, message, history, reveal_diagnostics=False, thread_id=None):
        self.calls.append(
            {
                "message": message,
                "history": history,
                "reveal_diagnostics": reveal_diagnostics,
                "thread_id": thread_id,
            }
        )
        yield [{"role": "assistant", "content": "正在整理回答"}]
        yield [{"role": "assistant", "content": f"回答：{message}"}]

    def clear_session(self, thread_id=None):
        self.rag_system.reset_thread(thread_id)


class FakeContainer:
    def __init__(self):
        self.rag_system = FakeRagSystem()
        self.chat_interface = FakeChatInterface(self.rag_system)
        self.chat_lock = threading.Lock()


class ApiAppTests(unittest.TestCase):
    def setUp(self):
        self.container = FakeContainer()
        set_container_for_tests(self.container)
        self.client = TestClient(create_app())

    def tearDown(self):
        set_container_for_tests(None)

    def test_create_session_accepts_existing_thread_id(self):
        response = self.client.post("/api/chat/session", json={"thread_id": "thread-123"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["thread_id"], "thread-123")

    def test_system_status_includes_knowledge_base_status(self):
        response = self.client.get("/api/system/status")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "ready")
        self.assertEqual(data["knowledge_base"]["status"], "ready")
        self.assertEqual(data["knowledge_base"]["stats"]["documents"], 2)

    def test_chat_history_returns_visible_messages(self):
        response = self.client.get("/api/chat/history", params={"thread_id": "thread-abc"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["thread_id"], "thread-abc")
        self.assertEqual([item["role"] for item in data["messages"]], ["user", "assistant"])

    def test_clear_session_uses_requested_thread_id(self):
        response = self.client.post("/api/chat/clear", json={"thread_id": "thread-clear"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.container.rag_system.cleared, ["thread-clear"])

    def test_chat_stream_emits_session_message_and_final_events(self):
        with self.client.stream(
            "GET",
            "/api/chat/stream",
            params={"thread_id": "thread-stream", "message": "高血压要注意什么"},
        ) as response:
            body = response.read().decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: session", body)
        self.assertIn("event: message", body)
        self.assertIn("event: final", body)
        self.assertNotIn("event: error", body)
        self.assertIn("thread-stream", body)
        self.assertEqual(self.container.chat_interface.calls[0]["thread_id"], "thread-stream")


if __name__ == "__main__":
    unittest.main()
