import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

import psycopg  # noqa: E402

import config  # noqa: E402
from db.schema_manager import SchemaManager  # noqa: E402
from rag_agent.clinical_safety import (  # noqa: E402
    build_allergy_conflict_note,
    extract_allergens,
)
from services.appointment_service import AppointmentService  # noqa: E402


class AllergyCrossCheckTests(unittest.TestCase):
    """Memory x safety: warn when an answer mentions a known allergen."""

    def test_extract_allergens_from_memory_text(self):
        self.assertEqual(extract_allergens("偏好心内科；对青霉素过敏"), ["青霉素"])
        self.assertEqual(extract_allergens("对青霉素类药物过敏，对头孢过敏"), ["青霉素", "头孢"])
        self.assertEqual(extract_allergens("无已知过敏史"), [])

    def test_conflict_note_when_answer_mentions_allergen(self):
        note = build_allergy_conflict_note("对青霉素过敏", "轻症可考虑青霉素类抗生素治疗。")
        self.assertIn("过敏提醒", note)
        self.assertIn("青霉素", note)

    def test_no_note_when_no_overlap(self):
        self.assertEqual(build_allergy_conflict_note("对青霉素过敏", "建议多喝水多休息。"), "")

    def test_no_note_without_memories(self):
        self.assertEqual(build_allergy_conflict_note("", "可使用青霉素。"), "")


class _FakeCursor:
    def __init__(self, conn):
        self._conn = conn
        self._last = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(str(sql).split())
        if "UPDATE doctor_schedules" in normalized:
            self._last = (7,)
        elif "INSERT INTO appointments (" in normalized:
            raise psycopg.errors.UniqueViolation("duplicate key value violates uq_appointments_active_slot")
        elif "SELECT appointment_no" in normalized:
            self._last = ("APT-EXISTING99", date(2026, 8, 1), "上午")
        else:
            self._last = None

    def fetchone(self):
        return self._last


class _FakeConn:
    def __init__(self):
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        pass

    def rollback(self):
        self.rolled_back = True


class _IdempotentServiceHarness(AppointmentService):
    """AppointmentService with DB and lookups faked for the duplicate path."""

    def __init__(self):
        self.last_conn = None

    def _connect(self):
        self.last_conn = _FakeConn()
        return self.last_conn

    def ensure_patient_for_thread(self, thread_id, conn=None):
        return 42

    def find_available_schedule(self, *args, **kwargs):
        return {
            "schedule_id": 7,
            "doctor_id": 1,
            "department_id": 2,
            "schedule_date": date(2026, 8, 1),
            "time_slot": "上午",
            "department_name": "呼吸内科",
            "doctor_name": "张三",
        }


class AppointmentDbIdempotencyTests(unittest.TestCase):
    def test_duplicate_booking_returns_existing_appointment(self):
        service = _IdempotentServiceHarness()
        result = service.create_appointment("thread-1", "呼吸内科", date(2026, 8, 1), "上午")
        self.assertIsNotNone(result)
        self.assertTrue(result["already_booked"])
        self.assertEqual(result["appointment_no"], "APT-EXISTING99")
        # Rollback must fire so the quota decrement is reverted.
        self.assertTrue(service.last_conn.rolled_back)

    def test_migration_defines_partial_unique_index(self):
        versions = {version for version, _desc, _stmts in SchemaManager._MIGRATIONS}
        self.assertIn("021_appointments_idempotency", versions)
        statements = " ".join(
            " ".join(stmts)
            for version, _desc, stmts in SchemaManager._MIGRATIONS
            if version == "021_appointments_idempotency"
        )
        self.assertIn("UNIQUE INDEX", statements)
        self.assertIn("WHERE status = 'booked'", statements)


if __name__ == "__main__":
    unittest.main()
