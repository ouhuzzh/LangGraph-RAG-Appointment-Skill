import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

from rag_agent.date_utils import _normalize_date, _normalize_time_slot  # noqa: E402


class NormalizeTimeSlotTests(unittest.TestCase):
    def test_hhmm_passthrough(self):
        self.assertEqual(_normalize_time_slot("14:30"), "14:30")

    def test_hour_range_chinese(self):
        self.assertEqual(_normalize_time_slot("14点-15点"), "14:00–15:00")

    def test_single_hour(self):
        self.assertEqual(_normalize_time_slot("14点"), "14:00")

    def test_half_hour(self):
        self.assertEqual(_normalize_time_slot("14点半"), "14:30")

    def test_chinese_afternoon_hour(self):
        self.assertEqual(_normalize_time_slot("下午三点"), "15:00")

    def test_chinese_evening_hour(self):
        self.assertEqual(_normalize_time_slot("晚上八点"), "20:00")

    def test_chinese_noon(self):
        self.assertEqual(_normalize_time_slot("中午十二点"), "12:00")

    def test_empty_input(self):
        self.assertEqual(_normalize_time_slot(""), "")


class NormalizeDateTests(unittest.TestCase):
    def test_iso_passthrough(self):
        self.assertEqual(_normalize_date("2026-08-01"), "2026-08-01")

    def test_chinese_full_date(self):
        self.assertEqual(_normalize_date("2026年8月15日"), "2026-08-15")

    def test_slash_date(self):
        self.assertEqual(_normalize_date("2026/8/15"), "2026-08-15")

    def test_dot_date(self):
        self.assertEqual(_normalize_date("2026.8.15"), "2026-08-15")

    def test_invalid_date_returns_empty(self):
        self.assertEqual(_normalize_date("2026年13月45日"), "")

    def test_unparseable_returns_empty(self):
        self.assertEqual(_normalize_date("随便什么时候"), "")

    def test_today(self):
        self.assertEqual(_normalize_date("今天"), date.today().isoformat())

    def test_tomorrow(self):
        self.assertEqual(_normalize_date("明天"), (date.today() + timedelta(days=1)).isoformat())

    def test_day_after_tomorrow(self):
        self.assertEqual(_normalize_date("后天"), (date.today() + timedelta(days=2)).isoformat())

    def test_three_days_from_now_regression(self):
        # Regression: "大后天" contains the substring "后天"; the check order
        # previously resolved it to +2 days instead of +3.
        self.assertEqual(_normalize_date("大后天"), (date.today() + timedelta(days=3)).isoformat())

    def test_next_week_wednesday_is_in_future(self):
        result = _normalize_date("下周三")
        self.assertTrue(result)
        parsed = date.fromisoformat(result)
        self.assertGreater(parsed, date.today())
        self.assertEqual(parsed.weekday(), 2)  # Wednesday

    def test_this_week_day_never_in_past(self):
        result = _normalize_date("周五")
        self.assertTrue(result)
        parsed = date.fromisoformat(result)
        self.assertGreater(parsed, date.today())
        self.assertEqual(parsed.weekday(), 4)  # Friday


if __name__ == "__main__":
    unittest.main()
