import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

import config  # noqa: E402
from rag_agent import classifiers  # noqa: E402
from services.appointment_skill.dialog_policy import (  # noqa: E402
    format_appointment_list,
    format_department_options,
    format_doctor_options,
    format_reschedule_preview,
)


class ClassifierTests(unittest.TestCase):
    def test_greeting_detection(self):
        self.assertTrue(classifiers._looks_like_greeting("你好"))
        self.assertTrue(classifiers._looks_like_greeting("hello"))
        self.assertFalse(classifiers._looks_like_greeting("高血压怎么办"))

    def test_department_question(self):
        self.assertTrue(classifiers._looks_like_department_question("胸痛挂什么科"))
        self.assertFalse(classifiers._looks_like_department_question("感冒了怎么办"))

    def test_medical_knowledge_question(self):
        self.assertTrue(classifiers._looks_like_medical_knowledge_question("高血压怎么办"))
        self.assertFalse(classifiers._looks_like_medical_knowledge_question("你好"))

    def test_explicit_cancel_intent(self):
        self.assertTrue(classifiers._looks_like_explicit_cancel_intent("取消预约"))
        self.assertFalse(classifiers._looks_like_explicit_cancel_intent("我要挂呼吸内科"))

    def test_department_name_only(self):
        self.assertTrue(classifiers._looks_like_department_name_only("呼吸内科"))
        self.assertFalse(classifiers._looks_like_department_name_only(
            "我想详细咨询一下呼吸内科最近一周的专家号安排情况"))

    def test_intent_for_clarification_target(self):
        self.assertEqual(classifiers._intent_for_clarification_target("department", "x"), "appointment")
        self.assertEqual(classifiers._intent_for_clarification_target("appointment_no", "x"), "cancel_appointment")
        self.assertEqual(classifiers._intent_for_clarification_target("unknown", "medical_rag"), "medical_rag")

    def test_clarification_response(self):
        self.assertTrue(classifiers._looks_like_clarification_response("确认预约"))
        self.assertTrue(classifiers._looks_like_clarification_response("呼吸内科"))
        self.assertFalse(classifiers._looks_like_clarification_response(
            "我想再详细描述一下我的症状情况，最近三天以来我一直觉得头晕并且伴有恶心想吐的感觉"))

    def test_infer_risk_level_delegates_to_canonical_guardrail(self):
        # Regression: this module used to carry an inline copy that silently
        # missed the P7 guardrail; it must now honor the flag like node_helpers.
        original = getattr(config, "ENABLE_CLINICAL_SAFETY_GUARDRAIL", False)
        config.ENABLE_CLINICAL_SAFETY_GUARDRAIL = True
        self.addCleanup(setattr, config, "ENABLE_CLINICAL_SAFETY_GUARDRAIL", original)
        # "剧烈头痛" is guardrail vocabulary, not in legacy HIGH_RISK_KEYWORDS.
        self.assertEqual(classifiers._infer_risk_level("突然剧烈头痛"), "high")

    def test_infer_risk_level_legacy_keywords_still_work(self):
        self.assertEqual(classifiers._infer_risk_level("我现在胸痛"), "high")
        self.assertEqual(classifiers._infer_risk_level("今天天气不错"), "normal")


class DialogPolicyTests(unittest.TestCase):
    def test_department_options_empty(self):
        self.assertIn("没有找到可用科室", format_department_options([]))

    def test_department_options_lists_names(self):
        text = format_department_options([{"name": "呼吸内科"}, {"name": "心内科"}])
        self.assertIn("1. **呼吸内科**", text)
        self.assertIn("2. **心内科**", text)

    def test_doctor_options_empty_mentions_department(self):
        self.assertIn("呼吸内科", format_doctor_options("呼吸内科", []))

    def test_doctor_options_caps_at_eight(self):
        options = [
            {"doctor_name": f"医生{i}", "schedule_date": "2026-08-01", "time_slot": "上午", "quota_available": 3}
            for i in range(12)
        ]
        text = format_doctor_options("呼吸内科", options)
        self.assertIn("8. **医生7**", text)
        self.assertNotIn("9. ", text)

    def test_appointment_list_formats_entries(self):
        items = [{
            "appointment_no": "APT001",
            "department": "呼吸内科",
            "appointment_date": date(2026, 8, 1),
            "time_slot": "上午",
            "doctor_name": "张三",
        }]
        text = format_appointment_list(items)
        self.assertIn("APT001", text)
        self.assertIn("2026-08-01", text)

    def test_reschedule_preview_without_alternatives(self):
        current = {"department": "呼吸内科", "appointment_date": date(2026, 8, 1), "time_slot": "上午"}
        self.assertIn("没找到更合适的替代时段", format_reschedule_preview(current, []))

    def test_reschedule_preview_with_alternatives(self):
        current = {"department": "呼吸内科", "appointment_date": date(2026, 8, 1), "time_slot": "上午"}
        alts = [{"doctor_name": "李四", "schedule_date": "2026-08-02", "time_slot": "下午", "quota_available": 2}]
        text = format_reschedule_preview(current, alts)
        self.assertIn("李四", text)
        self.assertIn("2026-08-02", text)


if __name__ == "__main__":
    unittest.main()
