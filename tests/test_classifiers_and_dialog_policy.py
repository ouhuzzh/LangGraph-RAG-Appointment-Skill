"""Tests for the live classifier heuristics (node_helpers / routing_nodes)
and the appointment dialog_policy formatters.

Note: the stale parallel-copy module ``rag_agent.classifiers`` was removed —
these tests target the canonical implementations the graph actually uses.
"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

import config  # noqa: E402
from rag_agent import node_helpers as nh  # noqa: E402
from rag_agent import routing_nodes as rn  # noqa: E402
from services.appointment_skill.dialog_policy import (  # noqa: E402
    format_appointment_list,
    format_department_options,
    format_doctor_options,
    format_reschedule_preview,
)


class ClassifierTests(unittest.TestCase):
    def test_greeting_detection(self):
        self.assertTrue(nh._looks_like_greeting("你好"))
        self.assertFalse(nh._looks_like_greeting("高血压怎么办"))

    def test_department_question(self):
        self.assertTrue(nh._looks_like_department_question("胸痛挂什么科"))
        self.assertFalse(nh._looks_like_department_question("感冒了怎么办"))

    def test_medical_knowledge_question(self):
        self.assertTrue(nh._looks_like_medical_knowledge_question("高血压怎么办"))
        self.assertFalse(nh._looks_like_medical_knowledge_question("你好"))

    def test_explicit_cancel_intent(self):
        self.assertTrue(nh._looks_like_explicit_cancel_intent("取消预约"))
        self.assertFalse(nh._looks_like_explicit_cancel_intent("我要挂呼吸内科"))

    def test_l1_appointment_intent_is_strict(self):
        # L1-strict by design: bare booking phrases without a concrete entity
        # are deferred to L2/L3 instead of hard-matching.
        self.assertFalse(nh._looks_like_explicit_appointment_intent("感冒了怎么办"))

    def test_department_name_only(self):
        self.assertTrue(rn._looks_like_department_name_only("呼吸内科"))
        self.assertFalse(rn._looks_like_department_name_only("感冒了怎么办"))

    def test_intent_for_clarification_target_maps_node_names(self):
        self.assertEqual(rn._intent_for_clarification_target("recommend_department", ""), "triage")
        self.assertEqual(rn._intent_for_clarification_target("handle_cancel_appointment", ""), "cancel_appointment")
        self.assertEqual(rn._intent_for_clarification_target("unknown", "medical_rag"), "medical_rag")

    def test_infer_risk_level_guardrail_delegation(self):
        original = getattr(config, "ENABLE_CLINICAL_SAFETY_GUARDRAIL", False)
        config.ENABLE_CLINICAL_SAFETY_GUARDRAIL = True
        self.addCleanup(setattr, config, "ENABLE_CLINICAL_SAFETY_GUARDRAIL", original)
        self.assertEqual(nh._infer_risk_level("突然剧烈头痛"), "high")

    def test_infer_risk_level_legacy_keywords_still_work(self):
        self.assertEqual(nh._infer_risk_level("我现在胸痛"), "high")
        self.assertEqual(nh._infer_risk_level("今天天气不错"), "normal")


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
