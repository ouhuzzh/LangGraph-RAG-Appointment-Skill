from __future__ import annotations

from datetime import date


class AppointmentCatalog:
    def __init__(self, appointment_service):
        self.appointment_service = appointment_service

    def list_departments(self, query: str = "", limit: int = 10):
        if hasattr(self.appointment_service, "list_departments"):
            return self.appointment_service.list_departments(query=query or None, limit=limit)
        return []

    def list_available_doctors(self, department: str, schedule_date: date, time_slot: str):
        return self.appointment_service.list_available_doctors(department, schedule_date, time_slot)

    def get_doctor_availability(
        self,
        doctor_name: str,
        *,
        department: str = "",
        schedule_date: date | None = None,
        time_slot: str = "",
        limit: int = 6,
    ):
        if hasattr(self.appointment_service, "get_doctor_availability"):
            return self.appointment_service.get_doctor_availability(
                doctor_name,
                department=department or None,
                schedule_date=schedule_date,
                time_slot=time_slot or None,
                limit=limit,
            )
        if department and schedule_date and time_slot:
            rows = self.list_available_doctors(department, schedule_date, time_slot)
            return [item for item in rows if str(item.get("doctor_name") or "").strip() == doctor_name][:limit]
        if department and hasattr(self.appointment_service, "list_available_doctors") and schedule_date and time_slot:
            rows = self.list_available_doctors(department, schedule_date, time_slot)
            return [item for item in rows if str(item.get("doctor_name") or "").strip() == doctor_name][:limit]
        return []

    def list_my_appointments(self, thread_id: str, limit: int = 8):
        if hasattr(self.appointment_service, "list_user_appointments"):
            return self.appointment_service.list_user_appointments(thread_id, limit=limit)
        if hasattr(self.appointment_service, "find_candidate_appointments"):
            return self.appointment_service.find_candidate_appointments(thread_id=thread_id)[:limit]
        return []

    def list_upcoming_availability(self, department: str, *, doctor_name: str = "", start_date: date | None = None, limit: int = 6):
        if hasattr(self.appointment_service, "list_upcoming_availability"):
            return self.appointment_service.list_upcoming_availability(
                department,
                doctor_name=doctor_name or None,
                start_date=start_date,
                limit=limit,
            )
        return []
