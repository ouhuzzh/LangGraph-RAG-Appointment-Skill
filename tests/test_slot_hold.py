import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

import config  # noqa: E402
from db.schema_manager import SchemaManager  # noqa: E402
from rag_agent import appointment_nodes  # noqa: E402
from services.appointment_service import AppointmentService  # noqa: E402


class _RecordingCursor:
    """Scripted cursor: routes each SQL to a canned response, records calls."""

    def __init__(self, conn, script):
        self._conn = conn
        self._script = script
        self._last = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(str(sql).split())
        self._conn.executed.append(normalized)
        self._last = None
        for marker, response in self._script:
            if marker in normalized:
                self._last = response
                return
        # default: no rows

    def fetchone(self):
        return self._last

    def fetchall(self):
        return self._last or []


class _RecordingConn:
    def __init__(self, script):
        self.script = script
        self.executed = []
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return _RecordingCursor(self, self.script)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


_SCHEDULE = {
    "schedule_id": 7,
    "doctor_id": 1,
    "department_id": 2,
    "schedule_date": date(2026, 8, 1),
    "time_slot": "上午",
    "quota_available": 3,
    "doctor_name": "张三",
    "department_name": "呼吸内科",
}


class _HoldHarness(AppointmentService):
    def __init__(self, script):
        self._script = script
        self.last_conn = None

    def _connect(self):
        self.last_conn = _RecordingConn(self._script)
        return self.last_conn

    def ensure_patient_for_thread(self, thread_id, conn=None):
        return 42

    def find_available_schedule(self, *args, **kwargs):
        return dict(_SCHEDULE)


class SlotHoldServiceTests(unittest.TestCase):
    def test_hold_slot_decrements_quota_and_records_hold(self):
        service = _HoldHarness(script=[("UPDATE doctor_schedules", (7,))])
        result = service.hold_slot("t1", "tok1", "呼吸内科", date(2026, 8, 1), "上午", ttl_minutes=10)
        self.assertEqual(result["schedule_id"], 7)
        executed = " || ".join(service.last_conn.executed)
        self.assertIn("quota_available = quota_available - 1", executed)
        self.assertIn("INSERT INTO appointment_holds", executed)
        self.assertTrue(service.last_conn.committed)

    def test_hold_slot_rolls_back_when_quota_gone(self):
        service = _HoldHarness(script=[])  # quota UPDATE matches no row
        result = service.hold_slot("t1", "tok1", "呼吸内科", date(2026, 8, 1), "上午")
        self.assertIsNone(result)
        self.assertTrue(service.last_conn.rolled_back)

    def test_release_hold_restores_quota_only_for_active_hold(self):
        service = _HoldHarness(script=[("SET status = 'released'", (7,))])
        self.assertTrue(service.release_hold("tok1"))
        executed = " || ".join(service.last_conn.executed)
        self.assertIn("quota_available = quota_available + 1", executed)

    def test_release_hold_missing_token_is_noop(self):
        service = _HoldHarness(script=[])
        self.assertFalse(service.release_hold("ghost"))
        executed = " || ".join(service.last_conn.executed)
        self.assertNotIn("quota_available = quota_available + 1", executed)

    def test_release_expired_holds_restores_each_quota(self):
        service = _HoldHarness(script=[("SET status = 'expired'", [(7,), (9,)])])
        count = service.release_expired_holds()
        self.assertEqual(count, 2)
        executed = service.last_conn.executed
        restores = [s for s in executed if "quota_available = quota_available + 1" in s]
        self.assertEqual(len(restores), 2)

    def test_create_appointment_converts_hold_without_second_decrement(self):
        schedule_row = (7, 1, 2, date(2026, 8, 1), "上午", 2, "张三", "呼吸内科")
        service = _HoldHarness(script=[
            ("SET status = 'converted'", (7,)),
            ("SELECT ds.id, ds.doctor_id", schedule_row),
            ("INSERT INTO appointments (", (321,)),
        ])
        result = service.create_appointment(
            "t1", "呼吸内科", date(2026, 8, 1), "上午", hold_token="tok1",
        )
        self.assertEqual(result["status"], "booked")
        executed = " || ".join(service.last_conn.executed)
        self.assertIn("SET status = 'converted'", executed)
        # Quota was reserved by the hold — booking must not decrement again.
        self.assertNotIn("quota_available = quota_available - 1", executed)

    def test_create_appointment_falls_back_when_hold_expired(self):
        service = _HoldHarness(script=[
            ("UPDATE doctor_schedules", (7,)),
            ("INSERT INTO appointments (", (321,)),
        ])
        result = service.create_appointment(
            "t1", "呼吸内科", date(2026, 8, 1), "上午", hold_token="expired-token",
        )
        self.assertEqual(result["status"], "booked")
        executed = " || ".join(service.last_conn.executed)
        # Legacy race-checked decrement path must engage.
        self.assertIn("quota_available = quota_available - 1", executed)


class GraphHoldHookTests(unittest.TestCase):
    def setUp(self):
        self._original = getattr(config, "ENABLE_SLOT_HOLD", False)
        self.addCleanup(setattr, config, "ENABLE_SLOT_HOLD", self._original)

    def test_preview_places_hold_when_enabled(self):
        config.ENABLE_SLOT_HOLD = True
        fake_service = MagicMock()
        fake_service.hold_slot.return_value = dict(_SCHEDULE)
        payload = {"department": "呼吸内科", "date": "2026-08-01", "time_slot": "上午", "doctor_name": "张三"}
        with patch.object(appointment_nodes, "_slot_hold_service", fake_service):
            pending = appointment_nodes._build_pending_confirmation(
                "appointment", payload, hold_thread_id="t1",
            )
        fake_service.hold_slot.assert_called_once()
        kwargs = fake_service.hold_slot.call_args.kwargs
        self.assertEqual(kwargs["hold_token"], pending["pending_confirmation_id"])
        self.assertEqual(kwargs["department"], "呼吸内科")
        self.assertTrue(pending["pending_action_payload"]["slot_held"])

    def test_preview_skips_hold_when_disabled(self):
        config.ENABLE_SLOT_HOLD = False
        fake_service = MagicMock()
        payload = {"department": "呼吸内科", "date": "2026-08-01", "time_slot": "上午"}
        with patch.object(appointment_nodes, "_slot_hold_service", fake_service):
            appointment_nodes._build_pending_confirmation("appointment", payload, hold_thread_id="t1")
        fake_service.hold_slot.assert_not_called()

    def test_preview_survives_hold_failure(self):
        config.ENABLE_SLOT_HOLD = True
        fake_service = MagicMock()
        fake_service.hold_slot.side_effect = RuntimeError("db down")
        payload = {"department": "呼吸内科", "date": "2026-08-01", "time_slot": "上午"}
        with patch.object(appointment_nodes, "_slot_hold_service", fake_service):
            pending = appointment_nodes._build_pending_confirmation(
                "appointment", payload, hold_thread_id="t1",
            )
        self.assertTrue(pending["pending_confirmation_id"])
        self.assertNotIn("slot_held", pending["pending_action_payload"])

    def test_abort_releases_hold(self):
        config.ENABLE_SLOT_HOLD = True
        fake_service = MagicMock()
        with patch.object(appointment_nodes, "_slot_hold_service", fake_service):
            appointment_nodes._release_slot_hold({"pending_confirmation_id": "tok-9"})
        fake_service.release_hold.assert_called_once_with("tok-9")


class MigrationTests(unittest.TestCase):
    def test_migration_defines_holds_table_and_expiry_index(self):
        versions = {version for version, _desc, _stmts in SchemaManager._MIGRATIONS}
        self.assertIn("022_appointment_holds", versions)
        statements = " ".join(
            " ".join(stmts)
            for version, _desc, stmts in SchemaManager._MIGRATIONS
            if version == "022_appointment_holds"
        )
        self.assertIn("appointment_holds", statements)
        self.assertIn("expires_at", statements)
        self.assertIn("idx_appointment_holds_expiry", statements)


if __name__ == "__main__":
    unittest.main()
