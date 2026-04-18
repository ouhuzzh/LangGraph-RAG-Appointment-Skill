import sys
import unittest

sys.path.insert(0, r"D:\nageoffer\agentic-rag-for-dummies\project")

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
from rag_agent.edges import route_after_action, route_after_orchestrator_call, route_after_prepare_secondary_turn, route_after_rewrite  # noqa: E402
from rag_agent.nodes import analyze_turn, prepare_secondary_turn  # noqa: E402


class RoutingEdgeTests(unittest.TestCase):
    def test_analyze_turn_splits_supported_compound_request(self):
        result = analyze_turn(
            {
                "messages": [HumanMessage(content="取消刚才那个预约，然后我这个咳嗽还要看吗")],
                "conversation_summary": "",
                "pending_action_type": "",
                "pending_candidates": [],
                "pending_clarification": "",
                "clarification_target": "",
                "appointment_context": {},
                "recommended_department": "",
                "topic_focus": "",
            }
        )

        self.assertEqual(result["primary_intent"], "cancel_appointment")
        self.assertEqual(result["secondary_intent"], "medical_rag")
        self.assertEqual(result["deferred_user_question"], "我这个咳嗽还要看吗")

    def test_analyze_turn_splits_appointment_then_medical_follow_up(self):
        result = analyze_turn(
            {
                "messages": [HumanMessage(content="帮我挂呼吸内科，另外高血压药还要不要继续吃？")],
                "conversation_summary": "",
                "pending_action_type": "",
                "pending_candidates": [],
                "pending_clarification": "",
                "clarification_target": "",
                "appointment_context": {},
                "recommended_department": "",
                "topic_focus": "",
            }
        )

        self.assertEqual(result["primary_intent"], "appointment")
        self.assertEqual(result["secondary_intent"], "medical_rag")
        self.assertEqual(result["deferred_user_question"], "高血压药还要不要继续吃？")

    def test_analyze_turn_splits_triage_then_medical_question(self):
        result = analyze_turn(
            {
                "messages": [HumanMessage(content="我发烧咳嗽挂什么科，然后流感怎么预防？")],
                "conversation_summary": "",
                "pending_action_type": "",
                "pending_candidates": [],
                "pending_clarification": "",
                "clarification_target": "",
                "appointment_context": {},
                "recommended_department": "",
                "topic_focus": "",
            }
        )

        self.assertEqual(result["primary_intent"], "triage")
        self.assertEqual(result["secondary_intent"], "medical_rag")
        self.assertEqual(result["deferred_user_question"], "流感怎么预防？")

    def test_route_after_rewrite_passes_recent_context_to_agent_subgraph(self):
        sends = route_after_rewrite(
            {
                "questionIsClear": True,
                "conversation_summary": "用户在咨询高血压。",
                "recent_context": "User: 高血压会头晕吗\nAssistant: 有时会。",
                "rewrittenQuestions": ["高血压应该注意什么"],
            }
        )

        self.assertEqual(len(sends), 1)
        payload = sends[0].arg
        self.assertEqual(payload["question"], "高血压应该注意什么")
        self.assertEqual(payload["recent_context"], "User: 高血压会头晕吗\nAssistant: 有时会。")

    def test_route_after_action_prepares_secondary_turn_when_primary_is_done(self):
        decision = route_after_action(
            {
                "secondary_intent": "medical_rag",
                "deferred_user_question": "我这个咳嗽还要看吗",
                "pending_clarification": "",
                "pending_action_type": "",
            }
        )

        self.assertEqual(decision, "prepare_secondary_turn")

    def test_prepare_secondary_turn_resets_secondary_state(self):
        update = prepare_secondary_turn(
            {
                "secondary_intent": "appointment",
                "deferred_user_question": "帮我挂呼吸内科，明天下午",
            }
        )

        self.assertEqual(update["intent"], "appointment")
        self.assertEqual(update["primary_intent"], "appointment")
        self.assertEqual(update["deferred_user_question"], "")
        self.assertEqual(route_after_prepare_secondary_turn(update), "handle_appointment")

    def test_route_after_orchestrator_falls_back_after_repeated_no_evidence(self):
        decision = route_after_orchestrator_call(
            {
                "iteration_count": 2,
                "tool_call_count": 2,
                "messages": [
                    ToolMessage(content="NO_EVIDENCE: nothing", tool_call_id="tc1"),
                    ToolMessage(content="NO_EVIDENCE: still nothing", tool_call_id="tc2"),
                    AIMessage(content="", tool_calls=[{"id": "search-1", "name": "search_child_chunks", "args": {"query": "高血压"}}]),
                ],
            }
        )

        self.assertEqual(decision, "fallback_response")

    def test_route_after_orchestrator_falls_back_after_repeated_same_search_query(self):
        decision = route_after_orchestrator_call(
            {
                "iteration_count": 2,
                "tool_call_count": 2,
                "messages": [
                    AIMessage(content="", tool_calls=[{"id": "search-1", "name": "search_child_chunks", "args": {"query": "高血压症状"}}]),
                    ToolMessage(content="NO_EVIDENCE: nothing", tool_call_id="tc1"),
                    AIMessage(content="", tool_calls=[{"id": "search-2", "name": "search_child_chunks", "args": {"query": "高血压症状"}}]),
                ],
            }
        )

        self.assertEqual(decision, "fallback_response")


if __name__ == "__main__":
    unittest.main()
