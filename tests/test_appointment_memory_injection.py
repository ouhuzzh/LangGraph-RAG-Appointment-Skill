import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

from rag_agent import appointment_nodes  # noqa: E402


class _CapturingLLM:
    """Captures the HumanMessage payload the node builds, returns no tool call."""

    def __init__(self):
        self.captured = ""

    def with_config(self, **kwargs):
        return self

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        for msg in messages:
            self.captured += str(getattr(msg, "content", ""))
        return MagicMock(tool_calls=[])


class AppointmentMemoryInjectionTests(unittest.TestCase):
    """Regression: appointment slot-filling must see long-term user_memories so
    a user's usual department/preferences can pre-fill the booking request.
    Previously the request builder ignored state['user_memories']."""

    def test_user_memories_injected_into_skill_request(self):
        llm = _CapturingLLM()
        state = {
            "user_memories": "偏好心内科李医生；对青霉素过敏",
            "conversation_summary": "",
            "intent": "appointment",
        }
        appointment_nodes._invoke_appointment_skill_request(llm, state, "帮我挂号")
        self.assertIn("心内科李医生", llm.captured)
        self.assertIn("Known user context", llm.captured)

    def test_no_memories_section_when_absent(self):
        llm = _CapturingLLM()
        state = {"user_memories": "", "conversation_summary": "", "intent": "appointment"}
        appointment_nodes._invoke_appointment_skill_request(llm, state, "帮我挂号")
        self.assertNotIn("Known user context", llm.captured)


if __name__ == "__main__":
    unittest.main()
