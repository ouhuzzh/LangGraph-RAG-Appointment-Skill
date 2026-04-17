import sys
import unittest

sys.path.insert(0, r"D:\nageoffer\agentic-rag-for-dummies\project")

from langchain_core.messages import HumanMessage  # noqa: E402
from rag_agent.nodes import intent_router, rewrite_query, recommend_department  # noqa: E402
from rag_agent.schemas import IntentAnalysis, QueryAnalysis, DepartmentRecommendation  # noqa: E402


class FakeStructuredLLM:
    def __init__(self, responses):
        self.responses = list(responses)

    def with_config(self, **kwargs):
        return self

    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        return self.responses.pop(0)


class TranscriptRegressionTests(unittest.TestCase):
    def test_intent_router_treats_follow_up_medical_question_as_medical_rag(self):
        llm = FakeStructuredLLM(
            [
                IntentAnalysis(intent="clarification", is_clear=False, clarification_needed="请再详细一点"),
            ]
        )
        state = {
            "messages": [HumanMessage(content="那会头晕吗")],
            "conversation_summary": "用户正在询问高血压的常见表现和头晕是否相关。",
            "pending_action_type": "",
            "pending_candidates": [],
        }

        result = intent_router(state, llm)

        self.assertEqual(result["intent"], "medical_rag")
        self.assertEqual(result["pending_clarification"], "")

    def test_rewrite_query_accepts_contextual_follow_up_without_extra_clarification(self):
        llm = FakeStructuredLLM(
            [
                QueryAnalysis(is_clear=False, questions=[], clarification_needed="请说明你指的是哪种疾病"),
            ]
        )
        state = {
            "messages": [HumanMessage(content="那应该注意什么")],
            "conversation_summary": "用户刚刚询问糖尿病的常见症状与日常管理。",
            "intent": "medical_rag",
        }

        result = rewrite_query(state, llm)

        self.assertTrue(result["questionIsClear"])
        self.assertEqual(result["pending_clarification"], "")
        self.assertTrue(result["rewrittenQuestions"])

    def test_recommend_department_defaults_to_emergency_when_high_risk_and_model_wants_clarification(self):
        llm = FakeStructuredLLM(
            [
                DepartmentRecommendation(
                    department="",
                    reason="",
                    needs_clarification=True,
                    clarification_needed="胸痛持续多久了？",
                )
            ]
        )
        state = {
            "messages": [HumanMessage(content="我现在胸痛还有点呼吸困难")],
            "risk_level": "high",
            "appointment_context": {},
        }

        result = recommend_department(state, llm)

        self.assertEqual(result["recommended_department"], "急诊科")
        self.assertIn("急诊科", result["messages"][0].content)
        self.assertEqual(result["pending_clarification"], "")


if __name__ == "__main__":
    unittest.main()
