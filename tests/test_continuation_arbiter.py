import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

import config  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402

from rag_agent import routing_nodes  # noqa: E402
from rag_agent.continuation_arbiter import judge_continuation  # noqa: E402


class _FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def with_config(self, **kwargs):
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return MagicMock(content=self.reply)


class JudgeContinuationTests(unittest.TestCase):
    def test_yes_verdict(self):
        llm = _FakeLLM("是")
        payload = {"department": "呼吸内科", "date": "2026-08-01", "time_slot": "上午"}
        self.assertTrue(judge_continuation("appointment", payload, "行，就他了", llm=llm))
        self.assertIn("呼吸内科", llm.prompts[0])
        self.assertIn("行，就他了", llm.prompts[0])

    def test_no_verdict(self):
        self.assertFalse(judge_continuation("appointment", {}, "帮我推荐本书", llm=_FakeLLM("否")))

    def test_llm_failure_is_fail_open(self):
        self.assertFalse(judge_continuation("appointment", {}, "行", llm=_FakeLLM(RuntimeError("down"))))


def _pending_state(user_query: str) -> dict:
    return {
        "messages": [HumanMessage(content=user_query)],
        "pending_action_type": "appointment",
        "pending_action_payload": {"department": "呼吸内科", "date": "2026-08-01", "time_slot": "上午"},
        "pending_confirmation_id": "tok1",
        "pending_candidates": [],
        "pending_clarification": "",
        "clarification_target": "",
        "pending_stale_count": 0,
        "conversation_summary": "",
        "topic_focus": "",
        "appointment_context": {},
        "recommended_department": "",
        "recent_context": "",
        "intent": "appointment",
        "user_memories": "",
    }


class AnalyzeTurnArbiterTests(unittest.TestCase):
    """The arbiter only fires in the narrow band: flag on + rules missed +
    short signal-free reply. Its yes-verdict routes with a distinct reason."""

    def setUp(self):
        self._original = getattr(config, "ENABLE_LLM_CONTINUATION_ARBITER", False)
        self.addCleanup(setattr, config, "ENABLE_LLM_CONTINUATION_ARBITER", self._original)

    def test_arbiter_yes_resumes_with_llm_reason(self):
        config.ENABLE_LLM_CONTINUATION_ARBITER = True
        with patch("rag_agent.continuation_arbiter.judge_continuation", return_value=True) as judge:
            result = routing_nodes.analyze_turn(_pending_state("行就他了"))
        judge.assert_called_once()
        self.assertEqual(result.get("route_reason"), "continue_pending_action_llm")
        self.assertEqual(result.get("primary_intent"), "appointment")
        self.assertEqual(result.get("pending_stale_count"), 0)

    def test_arbiter_no_falls_through_to_fresh_turn(self):
        config.ENABLE_LLM_CONTINUATION_ARBITER = True
        with patch("rag_agent.continuation_arbiter.judge_continuation", return_value=False):
            result = routing_nodes.analyze_turn(_pending_state("嗯这样啊"))
        self.assertEqual(result.get("route_reason"), "turn_planner")
        self.assertEqual(result.get("pending_stale_count"), 1)

    def test_flag_off_never_calls_llm(self):
        config.ENABLE_LLM_CONTINUATION_ARBITER = False
        with patch("rag_agent.continuation_arbiter.judge_continuation") as judge:
            result = routing_nodes.analyze_turn(_pending_state("行就他了"))
        judge.assert_not_called()
        self.assertEqual(result.get("route_reason"), "turn_planner")

    def test_long_question_never_reaches_llm(self):
        # Band guard: question-shaped input is a topic switch by shape.
        config.ENABLE_LLM_CONTINUATION_ARBITER = True
        with patch("rag_agent.continuation_arbiter.judge_continuation") as judge:
            result = routing_nodes.analyze_turn(_pending_state("医生说高血压平时要注意什么"))
        judge.assert_not_called()
        self.assertEqual(result.get("route_reason"), "turn_planner")

    def test_rule_match_skips_llm(self):
        # Rules win first — the arbiter is a fallback, not a replacement.
        config.ENABLE_LLM_CONTINUATION_ARBITER = True
        with patch("rag_agent.continuation_arbiter.judge_continuation") as judge:
            result = routing_nodes.analyze_turn(_pending_state("确认预约"))
        judge.assert_not_called()
        self.assertEqual(result.get("route_reason"), "continue_pending_action")


if __name__ == "__main__":
    unittest.main()
