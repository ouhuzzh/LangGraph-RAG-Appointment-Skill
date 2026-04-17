import sys
import unittest

sys.path.insert(0, r"D:\nageoffer\agentic-rag-for-dummies\project")

from memory.redis_memory import RedisSessionMemory  # noqa: E402


class RedisSessionMemoryFallbackTests(unittest.TestCase):
    def test_in_process_fallback_keeps_recent_messages_and_state(self):
        memory = RedisSessionMemory()
        memory._enabled = False
        thread_id = "thread-fallback"

        count = memory.append_exchange(thread_id, "你好", "你好，我在。")
        memory.set_state(thread_id, {"intent": "medical_rag", "recommended_department": "全科医学科"})

        messages = memory.get_recent_messages(thread_id)
        state = memory.get_state(thread_id)

        self.assertEqual(count, 2)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].content, "你好")
        self.assertEqual(messages[1].content, "你好，我在。")
        self.assertEqual(state["recommended_department"], "全科医学科")

    def test_clear_session_removes_fallback_data(self):
        memory = RedisSessionMemory()
        memory._enabled = False
        thread_id = "thread-clear"
        memory.append_exchange(thread_id, "A", "B")
        memory.set_state(thread_id, {"intent": "appointment"})

        memory.clear_session(thread_id)

        self.assertEqual(memory.get_recent_messages(thread_id), [])
        self.assertEqual(memory.get_state(thread_id), {})


if __name__ == "__main__":
    unittest.main()
