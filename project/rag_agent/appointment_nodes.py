"""Appointment skill graph nodes and compatibility wrappers."""

from .legacy_nodes import (
    handle_appointment,
    handle_appointment_skill,
    handle_cancel_appointment,
)

__all__ = [
    "handle_appointment",
    "handle_appointment_skill",
    "handle_cancel_appointment",
]
