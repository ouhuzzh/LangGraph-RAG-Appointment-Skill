"""Shared LangGraph node helpers.

This module is the compatibility boundary for helpers that still live in
``nodes.py`` during the behavior-preserving split. New code should import from
this module instead of reaching into the monolithic node module directly.
"""

from .legacy_nodes import (
    _build_medical_fallback_notice,
    _build_recent_context,
    _confidence_bucket_explanation,
    _confidence_bucket_label,
    _extract_topic_focus,
    _format_reference_lines,
    _is_abort_request,
    _is_explicit_confirmation,
    _normalize_date,
    _normalize_time_slot,
    _pick_candidate_from_text,
    _sanitize_final_answer_text,
    _should_use_last_appointment,
)

__all__ = [
    "_build_medical_fallback_notice",
    "_build_recent_context",
    "_confidence_bucket_explanation",
    "_confidence_bucket_label",
    "_extract_topic_focus",
    "_format_reference_lines",
    "_is_abort_request",
    "_is_explicit_confirmation",
    "_normalize_date",
    "_normalize_time_slot",
    "_pick_candidate_from_text",
    "_sanitize_final_answer_text",
    "_should_use_last_appointment",
]
