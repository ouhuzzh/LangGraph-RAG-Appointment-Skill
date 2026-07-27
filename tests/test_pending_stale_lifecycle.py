import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

from langchain_core.messages import HumanMessage  # noqa: E402

from rag_agent.routing_nodes import analyze_turn, _should_continue_pending_action  # noqa: E402


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


class ContinuationCollisionTests(unittest.TestCase):
    """Regression: substring matching must not hijack long medical questions
    that incidentally contain weak booking cues (医生/时间/今天/先不...).
    A pending booking may only capture short slot-filling replies or
    sentences with strong booking verbs."""

    PENDING = {"pending_action_type": "appointment", "pending_candidates": []}

    def test_incidental_signals_do_not_hijack(self):
        collisions = [
            "那我先不吃阿司匹林了可以吗",      # abort word "先不" is incidental
            "医生说高血压平时要注意什么",      # weak cue 医生 in a question
            "高血压一般什么时间吃药比较好",    # weak cue 时间 in a question
            "今天头有点晕是怎么回事",          # date word 今天 in a question
            "我想了解一下取消订阅的健康影响",  # 取消 unrelated to booking
        ]
        for query in collisions:
            with self.subTest(query=query):
                self.assertFalse(_should_continue_pending_action(dict(self.PENDING), query))

    def test_genuine_continuations_still_match(self):
        continuations = [
            "确认预约",
            "好的那确认预约吧",
            "算了",                # short interjection = real abort
            "算了，先不预约了",    # canonical button abort text
            "换成下午的时段",
            "改到明天上午",
            "换个医生吧",          # short imperative slot reply
            "帮我换到周五",
        ]
        for query in continuations:
            with self.subTest(query=query):
                self.assertTrue(_should_continue_pending_action(dict(self.PENDING), query))


if __name__ == "__main__":
    unittest.main()
