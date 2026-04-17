from typing import List, Literal
from pydantic import BaseModel, Field

class QueryAnalysis(BaseModel):
    is_clear: bool = Field(
        description="Indicates if the user's question is clear and answerable."
    )
    questions: List[str] = Field(
        description="List of rewritten, self-contained questions."
    )
    clarification_needed: str = Field(
        description="Explanation if the question is unclear."
    )


class IntentAnalysis(BaseModel):
    intent: Literal["medical_rag", "triage", "appointment", "cancel_appointment", "clarification"] = Field(
        description="Intent classification. Must be one of: medical_rag, triage, appointment, cancel_appointment, clarification."
    )
    is_clear: bool = Field(
        description="Whether the user's request is clear enough to continue."
    )
    clarification_needed: str = Field(
        description="Clarification question if the request is not clear enough."
    )


class DepartmentRecommendation(BaseModel):
    department: str = Field(
        description="Single primary department recommendation."
    )
    reason: str = Field(
        description="Short reason for the department recommendation."
    )
    needs_clarification: bool = Field(
        description="Whether more information is required before making a recommendation."
    )
    clarification_needed: str = Field(
        description="Clarification question when more information is needed."
    )


class AppointmentRequest(BaseModel):
    department: str = Field(description="Department name if available, otherwise empty string.")
    date: str = Field(description="Appointment date phrase or ISO date string if available, otherwise empty string.")
    time_slot: str = Field(description="Preferred time slot such as 上午/下午/晚上 or morning/afternoon/evening, otherwise empty string.")
    doctor_name: str = Field(description="Doctor name if explicitly requested, otherwise empty string.")
    needs_clarification: bool = Field(description="Whether more information is required before booking.")
    clarification_needed: str = Field(description="Clarification question when required fields are missing.")


class CancelAppointmentRequest(BaseModel):
    appointment_no: str = Field(description="Appointment number if explicitly provided, otherwise empty string.")
    department: str = Field(description="Department name if available, otherwise empty string.")
    date: str = Field(description="Appointment date phrase or ISO date string if available, otherwise empty string.")
    needs_clarification: bool = Field(description="Whether more information is required before cancellation.")
    clarification_needed: str = Field(description="Clarification question when the appointment cannot be identified yet.")


class AppointmentActionCall(BaseModel):
    action: Literal["clarify", "prepare_booking"] = Field(
        description="Either ask for missing booking information or prepare a booking preview for confirmation."
    )
    department: str = Field(description="Department name if available, otherwise empty string.")
    date: str = Field(description="Appointment date phrase or ISO date string if available, otherwise empty string.")
    time_slot: str = Field(description="Preferred time slot if available, otherwise empty string.")
    doctor_name: str = Field(description="Doctor name if explicitly requested, otherwise empty string.")
    clarification: str = Field(description="Short clarification question when action is clarify, otherwise empty string.")


class CancelActionCall(BaseModel):
    action: Literal["clarify", "prepare_cancellation"] = Field(
        description="Either ask for missing cancellation information or prepare a cancellation preview for confirmation."
    )
    appointment_no: str = Field(description="Appointment number if available, otherwise empty string.")
    department: str = Field(description="Department name if available, otherwise empty string.")
    date: str = Field(description="Appointment date phrase or ISO date string if available, otherwise empty string.")
    clarification: str = Field(description="Short clarification question when action is clarify, otherwise empty string.")
