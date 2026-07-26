import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

from langchain_core.messages import HumanMessage  # noqa: E402

from rag_agent.routing_nodes import analyze_turn  # noqa: E402


def _pending_state(user_query: str, stale_count: int = 0) -> dict:
    return {
        "messages": [HumanMessage(content=user_query)],
        "pending_action_type": "appointment",
        "pending_action_payload": {"department": "呼吸内科"},
        "pending_confirmation_id": "abc123",
        "pending_candidates": [],
        "pending_clarification": "",
        "clarification_target": "",
        "pending_stale_count": stale_count,
        "conversation_summary": "",
        "topic_focus": "",
        "appointment_context": {},
        "recommended_department": "",
        "recent_context": "",
        "intent": "appointment",
        "user_memories": "",
    }


IRRELEVANT_QUERY = "推荐几本理财方面的书吧"


class PendingStaleLifecycleTests(unittest.TestCase):
    """Regression for the dead stale-exit: analyze_turn computed the incremented
    counter but never wrote it back, so pending_stale_count stayed 0 forever and
    the '2 irrelevant turns auto-clear' feature could never fire."""

    def test_first_irrelevant_turn_persists_counter(self):
        result = analyze_turn(_pending_state(IRRELEVANT_QUERY, stale_count=0))
        self.assertEqual(result.get("route_reason"), "turn_planner")
        self.assertEqual(result.get("pending_stale_count"), 1)

    def test_second_irrelevant_turn_triggers_stale_exit(self):
        result = analyze_turn(_pending_state(IRRELEVANT_QUERY, stale_count=1))
        self.assertEqual(result.get("route_reason"), "pending_stale_exit")
        self.assertEqual(result.get("pending_action_type"), "")
        self.assertEqual(result.get("pending_stale_count"), 0)

    def test_resuming_pending_resets_counter(self):
        result = analyze_turn(_pending_state("换成下午的时段", stale_count=1))
        self.assertEqual(result.get("route_reason"), "continue_pending_action")
        self.assertEqual(result.get("primary_intent"), "appointment")
        self.assertEqual(result.get("pending_stale_count"), 0)

    def test_confirmation_resumes_and_resets_counter(self):
        result = analyze_turn(_pending_state("确认预约", stale_count=1))
        self.assertEqual(result.get("route_reason"), "continue_pending_action")
        self.assertEqual(result.get("pending_stale_count"), 0)

    def test_no_pending_keeps_counter_zero(self):
        state = _pending_state(IRRELEVANT_QUERY)
        state["pending_action_type"] = ""
        state["pending_confirmation_id"] = ""
        result = analyze_turn(state)
        self.assertEqual(result.get("pending_stale_count"), 0)


if __name__ == "__main__":
    unittest.main()
