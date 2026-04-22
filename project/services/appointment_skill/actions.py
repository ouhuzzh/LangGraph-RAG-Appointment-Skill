from __future__ import annotations

from .schemas import AppointmentPreview, CancellationPreview, ReschedulePreview


def prepare_appointment_preview(schedule: dict) -> AppointmentPreview:
    return AppointmentPreview(
        department=schedule["department_name"],
        date=schedule["schedule_date"].isoformat(),
        time_slot=schedule["time_slot"],
        doctor_name=schedule.get("doctor_name") or "",
    )


def prepare_cancellation_preview(candidate: dict) -> CancellationPreview:
    return CancellationPreview(
        appointment_id=str(candidate["appointment_id"]),
        appointment_no=candidate["appointment_no"],
        department=candidate["department"],
        date=candidate["appointment_date"].isoformat(),
        time_slot=candidate["time_slot"],
        doctor_name=candidate.get("doctor_name") or "",
    )


def prepare_reschedule_preview(candidate: dict, schedule: dict) -> ReschedulePreview:
    return ReschedulePreview(
        appointment_id=str(candidate["appointment_id"]),
        appointment_no=candidate["appointment_no"],
        department=schedule["department_name"],
        date=schedule["schedule_date"].isoformat(),
        time_slot=schedule["time_slot"],
        doctor_name=schedule.get("doctor_name") or "",
        previous_department=candidate["department"],
        previous_date=candidate["appointment_date"].isoformat(),
        previous_time_slot=candidate["time_slot"],
        previous_doctor_name=candidate.get("doctor_name") or "",
    )
