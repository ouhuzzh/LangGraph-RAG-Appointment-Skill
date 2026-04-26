import sys
import threading
import unittest
from tempfile import TemporaryDirectory
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

    def record_import_event(self, event):
        self.last_import_event = event

    def refresh_knowledge_base_status(self):
        return self.get_knowledge_base_status()

    def start_knowledge_base_bootstrap(self):
        self.bootstrap_started = True


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


class FakeSyncResult:
    source = "nhc"
    label = "国家卫健委同步"
    written = 1
    updated = 0
    deactivated = 0
    unchanged = 0

    def to_event(self):
        return {
            "source": self.source,
            "label": self.label,
            "status": "completed",
            "written": self.written,
            "updated": self.updated,
            "deactivated": self.deactivated,
            "unchanged": self.unchanged,
            "failed": 0,
        }


class FakeDocumentManager:
    def __init__(self, temp_dir):
        self.markdown_dir = Path(temp_dir)
        (self.markdown_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")
        self.uploaded_paths = []
        self.synced = []

    def get_markdown_paths(self):
        return sorted(self.markdown_dir.glob("*.md"))

    def add_documents_with_report(self, paths):
        self.uploaded_paths = [Path(path).name for path in paths]
        return {
            "processed": len(paths),
            "added": len(paths),
            "updated": 0,
            "unchanged": 0,
            "deactivated": 0,
            "skipped": 0,
            "failed": 0,
            "sync_event": {
                "source": "local",
                "label": "本地文档同步",
                "status": "completed",
                "written": len(paths),
                "updated": 0,
                "deactivated": 0,
                "unchanged": 0,
                "failed": 0,
            },
        }

    def sync_official_source(self, source, limit=10, trigger_type="manual"):
        self.synced.append({"source": source, "limit": limit, "trigger_type": trigger_type})
        return FakeSyncResult()

    def get_official_source_coverage(self):
        return [
            {
                "source": "nhc",
                "label": "国家卫健委",
                "manifest_count": 4,
                "local_file_count": 1,
                "coverage_note": "测试覆盖度说明",
            }
        ]


class FakeContainer:
    def __init__(self, temp_dir):
        self.rag_system = FakeRagSystem()
        self.chat_interface = FakeChatInterface(self.rag_system)
        self.document_manager = FakeDocumentManager(temp_dir)
        self.chat_lock = threading.Lock()


class ApiAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.container = FakeContainer(self.tmp.name)
        set_container_for_tests(self.container)
        self.client = TestClient(create_app())

    def tearDown(self):
        set_container_for_tests(None)
        self.tmp.cleanup()

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

    def test_documents_status_list_and_tasks_are_user_facing(self):
        status_response = self.client.get("/api/documents/status")
        list_response = self.client.get("/api/documents/list")
        tasks_response = self.client.get("/api/documents/tasks")

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(tasks_response.status_code, 200)
        self.assertEqual(list_response.json()["documents"][0]["name"], "guide.md")
        self.assertEqual(tasks_response.json()["tasks"], [])
        self.assertEqual(status_response.json()["source_coverage"][0]["source"], "nhc")

    def test_documents_sources_returns_official_source_coverage(self):
        response = self.client.get("/api/documents/sources")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sources"][0]["manifest_count"], 4)

    def test_documents_upload_records_import_event(self):
        response = self.client.post(
            "/api/documents/upload",
            files=[("files", ("new-guide.md", b"# New Guide\n", "text/markdown"))],
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("已处理 1 个文件", data["message"])
        self.assertEqual(self.container.document_manager.uploaded_paths, ["new-guide.md"])
        self.assertEqual(self.container.rag_system.last_import_event["source"], "local")
        self.assertTrue(self.container.rag_system.bootstrap_started)

    def test_documents_sync_official_uses_document_manager(self):
        response = self.client.post(
            "/api/documents/sync-official",
            json={"source": "nhc", "limit": 2},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("官方同步完成", response.json()["message"])
        self.assertEqual(
            self.container.document_manager.synced,
            [{"source": "nhc", "limit": 2, "trigger_type": "manual"}],
        )


if __name__ == "__main__":
    unittest.main()
