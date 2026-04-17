import sys
import unittest
import uuid
from datetime import date, timedelta

sys.path.insert(0, r"D:\nageoffer\agentic-rag-for-dummies\project")

import psycopg  # noqa: E402
import config  # noqa: E402
from memory.summary_store import SummaryStore  # noqa: E402
from services.appointment_service import AppointmentService  # noqa: E402


def _db_available() -> bool:
    try:
        with psycopg.connect(
            host=config.POSTGRES_HOST,
            port=config.POSTGRES_PORT,
            dbname=config.POSTGRES_DB,
            user=config.POSTGRES_USER,
            password=config.POSTGRES_PASSWORD,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("select 1")
                cur.fetchone()
        return True
    except Exception:
        return False


@unittest.skipUnless(_db_available(), "PostgreSQL is unavailable for live integration tests.")
class LiveDatabaseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary_store = SummaryStore()
        cls.appointment_service = AppointmentService()

    def tearDown(self):
        if hasattr(self, "thread_id"):
            self._cleanup_thread(self.thread_id)

    def _cleanup_thread(self, thread_id: str):
        with psycopg.connect(
            host=config.POSTGRES_HOST,
            port=config.POSTGRES_PORT,
            dbname=config.POSTGRES_DB,
            user=config.POSTGRES_USER,
            password=config.POSTGRES_PASSWORD,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("select patient_id from chat_sessions where thread_id = %s", (thread_id,))
                row = cur.fetchone()
                patient_id = row[0] if row else None
                if patient_id:
                    cur.execute("delete from appointment_logs where appointment_id in (select id from appointments where patient_id = %s)", (patient_id,))
                    cur.execute("delete from appointments where patient_id = %s", (patient_id,))
                cur.execute("delete from chat_session_summaries where thread_id = %s", (thread_id,))
                cur.execute("delete from chat_sessions where thread_id = %s", (thread_id,))
                if patient_id:
                    cur.execute("delete from patients where id = %s", (patient_id,))
            conn.commit()

    def _find_future_schedule(self):
        for day_offset in range(0, 4):
            target_day = date.today() + timedelta(days=day_offset)
            schedule = self.appointment_service.find_available_schedule("呼吸内科", target_day, "morning", "张医生")
            if schedule:
                return schedule
        self.skipTest("No demo appointment schedule available in the next 4 days.")

    def test_summary_store_round_trip(self):
        self.thread_id = f"live-summary-{uuid.uuid4().hex[:12]}"
        self.summary_store.save_summary(self.thread_id, "第一次摘要", 2)
        self.summary_store.save_summary(self.thread_id, "第二次摘要", 4)

        saved = self.summary_store.get_summary(self.thread_id)

        self.assertEqual(saved, "第二次摘要")
        with psycopg.connect(
            host=config.POSTGRES_HOST,
            port=config.POSTGRES_PORT,
            dbname=config.POSTGRES_DB,
            user=config.POSTGRES_USER,
            password=config.POSTGRES_PASSWORD,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select count(*) from chat_session_summaries
                    where thread_id = %s and summary_type = 'long_term'
                    """,
                    (self.thread_id,),
                )
                count = cur.fetchone()[0]
        self.assertEqual(count, 1)

    def test_appointment_service_live_booking_and_cancellation(self):
        self.thread_id = f"live-appointment-{uuid.uuid4().hex[:12]}"
        schedule = self._find_future_schedule()

        booking = self.appointment_service.create_appointment(
            self.thread_id,
            "呼吸内科",
            schedule["schedule_date"],
            schedule["time_slot"],
            "张医生",
        )
        self.assertIsNotNone(booking)
        self.assertEqual(booking["department"], "呼吸内科")

        candidates = self.appointment_service.find_candidate_appointments(
            self.thread_id,
            appointment_no=booking["appointment_no"],
        )
        self.assertEqual(len(candidates), 1)

        cancelled = self.appointment_service.cancel_appointment(self.thread_id, candidates[0]["appointment_id"])
        self.assertIsNotNone(cancelled)
        self.assertEqual(cancelled["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
