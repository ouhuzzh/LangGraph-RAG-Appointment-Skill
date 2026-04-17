import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, r"D:\nageoffer\agentic-rag-for-dummies\project")

from rag_agent.nodes import (  # noqa: E402
    _normalize_date,
    _normalize_time_slot,
    _is_explicit_confirmation,
    _pick_candidate_from_text,
    _should_use_last_appointment,
)


class NodesHelperTests(unittest.TestCase):
    def test_normalize_date_supports_relative_weekday(self):
        today = date.today()
        expected = today + timedelta(days=(0 - today.weekday()) % 7 + 7)
        self.assertEqual(_normalize_date("下周一上午"), expected.isoformat())

    def test_normalize_date_supports_weekend(self):
        today = date.today()
        expected = today + timedelta(days=(5 - today.weekday()) % 7)
        self.assertEqual(_normalize_date("这个周末"), expected.isoformat())

    def test_normalize_date_rejects_invalid_date(self):
        self.assertEqual(_normalize_date("2026年13月1日"), "")

    def test_normalize_time_slot_supports_noon_and_embedded_phrase(self):
        self.assertEqual(_normalize_time_slot("中午12点"), "afternoon")
        self.assertEqual(_normalize_time_slot("周三上午"), "morning")
        self.assertEqual(_normalize_time_slot("morning"), "morning")

    def test_explicit_confirmation_is_strict(self):
        self.assertTrue(_is_explicit_confirmation("确认预约", "appointment"))
        self.assertTrue(_is_explicit_confirmation("确认取消", "cancel_appointment"))
        self.assertFalse(_is_explicit_confirmation("可以", "appointment"))

    def test_pick_candidate_from_text_supports_appointment_number_and_ordinal(self):
        candidates = [
            {"appointment_id": 1, "appointment_no": "APT111AAA"},
            {"appointment_id": 2, "appointment_no": "APT222BBB"},
        ]
        self.assertEqual(_pick_candidate_from_text("帮我取消 APT222BBB", candidates), candidates[1])
        self.assertEqual(_pick_candidate_from_text("取消第 1 个", candidates), candidates[0])

    def test_should_use_last_appointment_requires_explicit_recent_reference(self):
        self.assertTrue(_should_use_last_appointment("帮我取消最近的那个预约"))
        self.assertTrue(_should_use_last_appointment("取消上次那个"))
        self.assertFalse(_should_use_last_appointment("帮我取消预约"))


if __name__ == "__main__":
    unittest.main()
