from __future__ import annotations

from datetime import date, timedelta

from .actions import prepare_appointment_preview, prepare_cancellation_preview, prepare_reschedule_preview
from .catalog import AppointmentCatalog
from .dialog_policy import (
    format_appointment_list,
    format_department_options,
    format_doctor_options,
    format_doctor_schedule_options,
    format_reschedule_preview,
    format_upcoming_availability,
)
from .planner import suggest_alternative_doctors, suggest_alternative_slots


class AppointmentSkill:
    def __init__(self, appointment_service):
        self.appointment_service = appointment_service
        self.catalog = AppointmentCatalog(appointment_service)

    def discover_departments(self, query: str = "") -> str:
        departments = self.catalog.list_departments(query=query)
        return format_department_options(departments)

    def discover_department_availability(self, department: str) -> tuple[str, list[dict]]:
        upcoming = self.catalog.list_upcoming_availability(department, limit=6)
        return format_upcoming_availability(department, upcoming), upcoming

    def discover_doctors(self, department: str, schedule_date: date | None = None, time_slot: str = "") -> tuple[str, list[dict]]:
        if department and schedule_date and time_slot:
            doctors = self.catalog.list_available_doctors(department, schedule_date, time_slot)
        else:
            doctors = self.catalog.list_upcoming_availability(department, limit=6)
        return format_doctor_options(department, doctors), doctors

    def discover_doctor_availability(self, doctor_name: str, *, department: str = "", schedule_date: date | None = None, time_slot: str = "") -> tuple[str, list[dict]]:
        upcoming = self.catalog.get_doctor_availability(
            doctor_name,
            department=department,
            schedule_date=schedule_date,
            time_slot=time_slot,
            limit=6,
        )
        if not upcoming:
            return f"暂时没有找到 **{doctor_name}** 的可预约号源。你也可以告诉我科室，我帮你看看其他医生。", []
        header = f"我找到 **{doctor_name}** 当前可预约的时段："
        return format_doctor_schedule_options(department or upcoming[0]["department_name"], doctor_name, upcoming, lead=header), upcoming

    def list_my_appointments(self, thread_id: str) -> tuple[str, list[dict]]:
        appointments = self.catalog.list_my_appointments(thread_id)
        return format_appointment_list(appointments), appointments

    def prepare_appointment(self, *, department: str, schedule_date: date, time_slot: str, doctor_name: str = "", allow_any_doctor: bool = False):
        doctor_options = self.catalog.list_available_doctors(department, schedule_date, time_slot)
        if not doctor_options:
            alternatives = suggest_alternative_slots(
                self.catalog.list_upcoming_availability(department, doctor_name=doctor_name, start_date=schedule_date, limit=6)
            )
            return None, [], alternatives
        if not doctor_name and not allow_any_doctor and len(doctor_options) > 1:
            return None, doctor_options, []
        schedule = self.appointment_service.find_available_schedule(
            department=department,
            schedule_date=schedule_date,
            time_slot=time_slot,
            doctor_name=doctor_name or None,
        )
        if not schedule and doctor_name:
            alternatives = suggest_alternative_doctors(doctor_options, exclude_name=doctor_name)
            return None, alternatives, []
        if not schedule and doctor_options:
            schedule = doctor_options[0]
        if not schedule:
            return None, [], []
        return prepare_appointment_preview(schedule), doctor_options, []

    def confirm_appointment(self, thread_id: str, payload: dict):
        return self.appointment_service.create_appointment(
            thread_id=thread_id,
            department=payload["department"],
            schedule_date=date.fromisoformat(payload["date"]),
            time_slot=payload["time_slot"],
            doctor_name=payload.get("doctor_name") or None,
        )

    def prepare_cancellation(self, thread_id: str, *, appointment_no: str = "", department: str = "", schedule_date: date | None = None):
        if not appointment_no and not (department and schedule_date):
            appointments = self.catalog.list_my_appointments(thread_id)
            return None, appointments
        candidates = self.appointment_service.find_candidate_appointments(
            thread_id=thread_id,
            appointment_no=appointment_no or None,
            department=department or None,
            schedule_date=schedule_date,
        )
        if len(candidates) != 1:
            return None, candidates
        return prepare_cancellation_preview(candidates[0]), []

    def confirm_cancellation(self, thread_id: str, payload: dict):
        return self.appointment_service.cancel_appointment(thread_id, int(payload["appointment_id"]))

    def prepare_reschedule(self, thread_id: str, candidate: dict, target_date: date | None = None, time_slot: str = "") -> str:
        start_date = target_date or (candidate["appointment_date"] + timedelta(days=1))
        alternatives = suggest_alternative_slots(
            self.catalog.list_upcoming_availability(
                candidate["department"],
                doctor_name=candidate.get("doctor_name") or "",
                start_date=start_date,
                limit=6,
            )
        )
        return format_reschedule_preview(candidate, alternatives)

    def prepare_reschedule_preview(
        self,
        *,
        candidate: dict,
        target_date: date,
        time_slot: str,
        doctor_name: str = "",
        allow_any_doctor: bool = False,
    ):
        doctor_options = self.catalog.list_available_doctors(candidate["department"], target_date, time_slot)
        if not doctor_options:
            alternatives = suggest_alternative_slots(
                self.catalog.list_upcoming_availability(
                    candidate["department"],
                    doctor_name=doctor_name or "",
                    start_date=target_date,
                    limit=6,
                )
            )
            return None, [], alternatives
        if not doctor_name and not allow_any_doctor and len(doctor_options) > 1:
            return None, doctor_options, []
        schedule = self.appointment_service.find_available_schedule(
            candidate["department"],
            target_date,
            time_slot,
            doctor_name=doctor_name or None,
        )
        if not schedule and doctor_name:
            alternatives = suggest_alternative_doctors(doctor_options, exclude_name=doctor_name)
            return None, alternatives, []
        if not schedule and doctor_options:
            schedule = doctor_options[0]
        if not schedule:
            return None, [], []
        return prepare_reschedule_preview(candidate, schedule), doctor_options, []

    def confirm_reschedule(self, thread_id: str, payload: dict):
        return self.appointment_service.reschedule_appointment(
            thread_id=thread_id,
            appointment_id=int(payload["appointment_id"]),
            department=payload["department"],
            schedule_date=date.fromisoformat(payload["date"]),
            time_slot=payload["time_slot"],
            doctor_name=payload.get("doctor_name") or None,
        )
