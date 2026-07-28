from __future__ import annotations
"""Appointment skill private helpers.

Extracted from ``appointment_nodes`` to keep the public graph-node module
focused on entry-point wiring.  All private helpers — formatting, parsing,
legacy compatibility wrappers, skill internals, MCP discovery, and hospital
selection — live here.
"""

import uuid
import logging
from datetime import date

import config

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from .graph_state import State
from .schemas import (
    AppointmentActionCall,
    CancelActionCall,
    AppointmentSkillRequest,
)
from .prompts import get_appointment_request_prompt, get_cancel_appointment_prompt, get_appointment_skill_prompt
from db.appointment_skill_log_store import AppointmentSkillLogStore
from services.mcp_appointment_backend import MCPAppointmentBackend
from mcp_integration.hospital_selection import (
    MCPHospitalSelectionPolicy,
    format_hospital_confirmation,
    format_hospital_clarification,
)

from .node_helpers import (
    _build_appointment_context,
    _clear_pending_action_state,
    _get_appointment_context,
    _get_pending_payload,
    _get_user_query,
    _is_abort_request,
    _is_explicit_confirmation,
    _json_safe_value,
    _next_clarification_attempt,
    _normalize_date,
    _normalize_time_slot,
    _pick_candidate_from_text,
    _sanitize_pending_payload,
    _should_use_last_appointment,
    _wants_any_available_doctor,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Appointment-specific module-level state
# ---------------------------------------------------------------------------

_APPOINTMENT_SKILL_LOG_STORE = None
_slot_hold_service = None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_appointment_skill_log_store():
    global _APPOINTMENT_SKILL_LOG_STORE
    if _APPOINTMENT_SKILL_LOG_STORE is None:
        _APPOINTMENT_SKILL_LOG_STORE = AppointmentSkillLogStore()
    return _APPOINTMENT_SKILL_LOG_STORE


def _pick_doctor_name_from_text(user_query: str, doctor_options: list[dict] | None) -> str:
    normalized = (user_query or "").strip().lower()
    for item in doctor_options or []:
        doctor_name = str(item.get("doctor_name") or "").strip()
        if doctor_name and doctor_name.lower() in normalized:
            return doctor_name
    return ""


def _sort_schedule_options(options: list[dict]) -> list[dict]:
    return sorted(
        list(options or []),
        key=lambda item: (
            str(item.get("schedule_date") or ""),
            str(item.get("time_slot") or ""),
            str(item.get("doctor_name") or ""),
            int(item.get("schedule_id") or 0),
        ),
    )


def _find_matching_doctor_options(options: list[dict], doctor_name: str) -> list[dict]:
    doctor_name_normalized = str(doctor_name or "").strip().lower()
    if not doctor_name_normalized:
        return []
    return [
        item
        for item in (options or [])
        if doctor_name_normalized in str(item.get("doctor_name") or "").strip().lower()
    ]


def _schedule_to_preview_payload(schedule: dict, *, action: str = "book") -> dict:
    return {
        "department": schedule.get("department_name") or schedule.get("department") or "",
        "date": str(schedule.get("schedule_date") or ""),
        "time_slot": schedule.get("time_slot") or "",
        "doctor_name": schedule.get("doctor_name") or "",
        "action": action,
        "hospital_code": schedule.get("hospital_code") or "",
        "hospital_name": schedule.get("hospital_name") or "",
    }


def _format_doctor_slot_selection_message(department: str, doctor_name: str, options: list[dict]) -> str:
    lines = [
        f"{idx}. **{item.get('schedule_date')} {item.get('time_slot')}**（剩余号源 {item.get('quota_available', 0)}）"
        for idx, item in enumerate(_sort_schedule_options(options)[:8], start=1)
    ]
    return (
        f"我找到 **{department}** 的 **{doctor_name}** 可预约时段：\n\n"
        + "\n".join(lines)
        + "\n\n你可以直接回复具体日期和时段，例如\u201c2026-04-18 下午\u201d；如果你希望我直接优先选最早可用时段，也可以回复 **最早可用时段**。"
    )


def _format_doctor_options(department: str, normalized_date: str, time_slot: str, doctor_options: list[dict]) -> str:
    options = "\n".join(
        f"{idx}. **{item['doctor_name']}**（剩余号源 {item.get('quota_available', 0)}）"
        for idx, item in enumerate(doctor_options[:8], start=1)
    )
    return (
        f"目前 **{department}** 在 {normalized_date} {time_slot} 可预约的医生有：\n\n"
        f"{options}\n\n"
        "请直接回复医生姓名；如果你不挑医生，也可以回复 **任一可用医生**，我会为你自动安排。"
    )


def _parse_tool_call(response, expected_name: str) -> dict:
    tool_calls = getattr(response, "tool_calls", None) or []
    for tool_call in tool_calls:
        if tool_call.get("name") == expected_name:
            return tool_call.get("args") or {}
    return {}


def _build_pending_confirmation(action_type: str, payload: dict, *, hold_thread_id: str = "") -> dict:
    pending = {
        "pending_action_type": action_type,
        "pending_action_payload": _sanitize_pending_payload(payload),
        "pending_confirmation_id": uuid.uuid4().hex,
        "pending_candidates": [],
    }
    # Slot hold (local-DB bookings only — callers opt in via hold_thread_id):
    # reserve the quota at preview time so it cannot be raced away before the
    # user confirms. Fail-open: a hold failure never blocks the preview, and
    # superseded/abandoned holds are reclaimed by the TTL sweep.
    if (
        hold_thread_id
        and action_type == "appointment"
        and getattr(config, "ENABLE_SLOT_HOLD", False)
    ):
        try:
            held = _get_slot_hold_service().hold_slot(
                thread_id=hold_thread_id,
                hold_token=pending["pending_confirmation_id"],
                department=str(payload.get("department") or ""),
                schedule_date=date.fromisoformat(str(payload.get("date"))),
                time_slot=str(payload.get("time_slot") or ""),
                doctor_name=payload.get("doctor_name") or None,
                ttl_minutes=int(getattr(config, "SLOT_HOLD_TTL_MINUTES", 10)),
            )
            if held:
                pending["pending_action_payload"]["slot_held"] = True
        except Exception:
            logger.warning("Slot hold failed; preview continues without a hold", exc_info=True)
    return pending


def _get_slot_hold_service():
    """Lazy AppointmentService used for preview-time holds (test-injectable)."""
    global _slot_hold_service
    if _slot_hold_service is None:
        from services.appointment_service import AppointmentService
        _slot_hold_service = AppointmentService()
    return _slot_hold_service


def _release_slot_hold(state: State) -> None:
    """Return held quota when the user abandons a pending booking."""
    token = state.get("pending_confirmation_id", "")
    if not token or not getattr(config, "ENABLE_SLOT_HOLD", False):
        return
    try:
        _get_slot_hold_service().release_hold(token)
    except Exception:
        logger.debug("Slot hold release failed; TTL sweep will reclaim it", exc_info=True)


def _time_slot_label(slot: str) -> str:
    """Display label for a stored time-slot enum (morning/afternoon/evening)."""
    return {
        "morning": "上午",
        "afternoon": "下午",
        "evening": "晚间",
        "night": "晚间",
    }.get(str(slot or "").strip().lower(), str(slot or ""))


def _format_booking_preview(payload: dict) -> str:
    doctor_name = payload.get("doctor_name") or "不限"
    hospital_line = f"- 医院：**{payload['hospital_name']}**\n" if payload.get("hospital_name") else ""
    return (
        "我已经整理好预约信息，请回复 **确认预约** 来正式提交：\n\n"
        f"{hospital_line}"
        f"- 科室：**{payload['department']}**\n"
        f"- 日期：**{payload['date']}**\n"
        f"- 时段：**{_time_slot_label(payload['time_slot'])}**\n"
        f"- 医生：**{doctor_name}**\n\n"
        "如果你想改日期、时段、科室或医生，直接告诉我新的要求即可。"
    )


def _format_cancel_preview(payload: dict) -> str:
    hospital_line = f"- 医院：**{payload['hospital_name']}**\n" if payload.get("hospital_name") else ""
    return (
        "我已找到要取消的预约，请回复 **确认取消** 来正式提交：\n\n"
        f"{hospital_line}"
        f"- 预约号：**{payload['appointment_no']}**\n"
        f"- 科室：**{payload['department']}**\n"
        f"- 日期：**{payload['date']}**\n"
        f"- 时段：**{payload['time_slot']}**\n\n"
        "如果你想换一条预约取消，也可以直接告诉我新的预约号或条件。"
    )


def _format_reschedule_confirmation_preview(payload: dict) -> str:
    previous_doctor = payload.get("previous_doctor_name") or "未指定"
    next_doctor = payload.get("doctor_name") or "未指定"
    hospital_line = f"- 医院：**{payload['hospital_name']}**\n" if payload.get("hospital_name") else ""
    return (
        "我已整理好改约信息，请回复 **确认预约** 来正式提交改约：\n\n"
        f"{hospital_line}"
        f"- 原预约：**{payload['previous_department']}**，**{payload['previous_date']}**，**{payload['previous_time_slot']}**，医生：**{previous_doctor}**\n"
        f"- 新预约：**{payload['department']}**，**{payload['date']}**，**{payload['time_slot']}**，医生：**{next_doctor}**\n\n"
        "如果你想再换一个日期、时段或医生，直接告诉我新的要求即可。"
    )


# ---------------------------------------------------------------------------
# Legacy compatibility wrappers
# ---------------------------------------------------------------------------

def _handle_appointment_legacy(state: State, llm, appointment_service):
    user_query = _get_user_query(state)
    appointment_context = _get_appointment_context(state)
    pending_action_type = state.get("pending_action_type", "")
    pending_payload = _get_pending_payload(state)

    if pending_action_type == "appointment":
        if _is_abort_request(user_query):
            _release_slot_hold(state)
            return {
                "intent": "appointment",
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                "topic_focus": appointment_context.get("department", state.get("topic_focus", "")),
                "appointment_context": appointment_context,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content="好的，这次预约我先不提交了。你如果想改时间、科室或重新预约，直接告诉我即可。")],
            }

        if _is_explicit_confirmation(user_query, "appointment"):
            booking = appointment_service.create_appointment(
                thread_id=state["thread_id"],
                department=pending_payload["department"],
                schedule_date=date.fromisoformat(pending_payload["date"]),
                time_slot=pending_payload["time_slot"],
                doctor_name=pending_payload.get("doctor_name") or None,
                hold_token=state.get("pending_confirmation_id") or None,
            )
            merged_context = _build_appointment_context(appointment_context, pending_payload)
            if not booking:
                answer = (
                    f"刚刚确认时，**{pending_payload['department']}** 在 {pending_payload['date']} "
                    f"{pending_payload['time_slot']} 的号源已经不可用了。你可以换个日期、时段，或让我继续帮你改约。"
                )
                return {
                    "intent": "appointment",
                    "pending_clarification": "",
                    "clarification_target": "",
                    "clarification_attempts": 0,
                    "topic_focus": merged_context.get("department", state.get("topic_focus", "")),
                    "appointment_context": merged_context,
                    **_clear_pending_action_state(),
                    "messages": [AIMessage(content=answer)],
                }

            answer = (
                f"已为你预约成功：\n\n"
                f"- 科室：**{booking['department']}**\n"
                f"- 日期：**{booking['date']}**\n"
                f"- 时段：**{_time_slot_label(booking['time_slot'])}**\n"
                f"- 医生：**{booking['doctor_name']}**\n"
                f"- 预约号：**{booking['appointment_no']}**"
            )
            return {
                "intent": "appointment",
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                "topic_focus": merged_context.get("department", state.get("topic_focus", "")),
                "appointment_context": merged_context,
                "last_appointment_no": booking["appointment_no"],
                **_clear_pending_action_state(),
                "messages": [AIMessage(content=answer)],
            }

    llm_with_tools = llm.with_config(temperature=0.1).bind_tools([AppointmentActionCall])
    response = llm_with_tools.invoke(
        [
            SystemMessage(content=get_appointment_request_prompt()),
            HumanMessage(
                content=(
                    f"Conversation summary:\n{state.get('conversation_summary', '')}\n\n"
                    f"Recommended department:\n{state.get('recommended_department', '')}\n\n"
                    f"Existing appointment context:\n{appointment_context}\n\n"
                    f"User query:\n{user_query}"
                )
            ),
        ]
    )
    call_args = _parse_tool_call(response, "AppointmentActionCall")

    department = (call_args.get("department") or "").strip() or state.get("recommended_department", "") or appointment_context.get("department", "")
    normalized_date = _normalize_date(call_args.get("date") or appointment_context.get("date", "") or user_query)
    time_slot = _normalize_time_slot(call_args.get("time_slot") or appointment_context.get("time_slot", "") or user_query)
    available_doctors = appointment_context.get("available_doctors") or []
    doctor_name = (
        (call_args.get("doctor_name") or "").strip()
        or _pick_doctor_name_from_text(user_query, available_doctors)
        or appointment_context.get("doctor_name", "")
    )
    wants_any_doctor = _wants_any_available_doctor(user_query)

    merged_context = _build_appointment_context(
        appointment_context,
        {
            "department": department,
            "date": normalized_date,
            "time_slot": time_slot,
            "doctor_name": doctor_name,
            "available_doctors": available_doctors,
        },
    )

    missing_fields = []
    if not department:
        missing_fields.append("科室")
    if not normalized_date:
        missing_fields.append("日期")
    if not time_slot:
        missing_fields.append("时间段")

    if call_args.get("action") == "clarify" or missing_fields:
        clarification = (call_args.get("clarification") or "").strip() or f"请补充要预约的{'、'.join(missing_fields)}。"
        return {
            "intent": "appointment",
            "pending_clarification": clarification,
            "clarification_target": "handle_appointment",
            "clarification_attempts": _next_clarification_attempt(state),
            "topic_focus": department or state.get("topic_focus", ""),
            "appointment_context": merged_context,
            **_clear_pending_action_state(),
            "messages": [AIMessage(content=clarification)],
        }

    schedule_date_value = date.fromisoformat(normalized_date)
    doctor_options = appointment_service.list_available_doctors(
        department=department,
        schedule_date=schedule_date_value,
        time_slot=time_slot,
    )
    if not doctor_options:
        answer = f"暂时没有找到 **{department}** 在 {normalized_date} {time_slot} 的可预约号源。你可以换一个日期、时间段，或继续让我帮你改约。"
        return {
            "intent": "appointment",
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
            "topic_focus": department or state.get("topic_focus", ""),
            "appointment_context": _build_appointment_context(merged_context, {"available_doctors": []}),
            **_clear_pending_action_state(),
            "messages": [AIMessage(content=answer)],
        }

    if not doctor_name and len(doctor_options) > 1 and not wants_any_doctor:
        clarification = _format_doctor_options(department, normalized_date, time_slot, doctor_options)
        return {
            "intent": "appointment",
            "pending_clarification": clarification,
            "clarification_target": "handle_appointment",
            "clarification_attempts": _next_clarification_attempt(state),
            "topic_focus": department or state.get("topic_focus", ""),
            "appointment_context": _build_appointment_context(merged_context, {"available_doctors": doctor_options, "doctor_name": ""}),
            **_clear_pending_action_state(),
            "messages": [AIMessage(content=clarification)],
        }

    schedule = appointment_service.find_available_schedule(
        department=department,
        schedule_date=schedule_date_value,
        time_slot=time_slot,
        doctor_name=doctor_name or None,
    )
    if not schedule:
        if doctor_name and doctor_options:
            doctor_hint = _format_doctor_options(department, normalized_date, time_slot, doctor_options)
            answer = f"没有找到 **{doctor_name}** 在该时段的可预约号源。\n\n{doctor_hint}"
            return {
                "intent": "appointment",
                "pending_clarification": answer,
                "clarification_target": "handle_appointment",
                "clarification_attempts": _next_clarification_attempt(state),
                "topic_focus": department or state.get("topic_focus", ""),
                "appointment_context": _build_appointment_context(merged_context, {"available_doctors": doctor_options, "doctor_name": ""}),
                **_clear_pending_action_state(),
                "messages": [AIMessage(content=answer)],
            }
        answer = f"暂时没有找到 **{department}** 在 {normalized_date} {time_slot} 的可预约号源。你可以换一个日期、时间段，或继续让我帮你改约。"
        return {
            "intent": "appointment",
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
            "topic_focus": department or state.get("topic_focus", ""),
            "appointment_context": _build_appointment_context(merged_context, {"available_doctors": doctor_options}),
            **_clear_pending_action_state(),
            "messages": [AIMessage(content=answer)],
        }

    preview_payload = {
        "department": schedule["department_name"],
        "date": schedule["schedule_date"].isoformat(),
        "time_slot": schedule["time_slot"],
        "doctor_name": schedule["doctor_name"],
        "action": "book",
    }
    return {
        "intent": "appointment",
        "pending_clarification": "",
        "clarification_target": "",
        "clarification_attempts": 0,
        "topic_focus": preview_payload["department"],
        "appointment_context": _build_appointment_context(merged_context, {"available_doctors": doctor_options, "doctor_name": schedule["doctor_name"]}),
        **_build_pending_confirmation("appointment", preview_payload, hold_thread_id=state.get("thread_id", "")),
        "messages": [AIMessage(content=_format_booking_preview(preview_payload))],
    }


def _handle_cancel_appointment_legacy(state: State, llm, appointment_service):
    user_query = _get_user_query(state)
    appointment_context = _get_appointment_context(state)
    last_appointment_no = state.get("last_appointment_no", "")
    pending_action_type = state.get("pending_action_type", "")
    pending_payload = _get_pending_payload(state)
    pending_candidates = state.get("pending_candidates", []) or []

    if pending_action_type == "cancel_appointment":
        if _is_abort_request(user_query):
            return {
                "intent": "cancel_appointment",
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content="好的，这次取消我先不提交了。如果你想改成别的预约，直接告诉我新的预约号或条件即可。")],
            }

        if _is_explicit_confirmation(user_query, "cancel_appointment"):
            cancelled = appointment_service.cancel_appointment(state["thread_id"], int(pending_payload["appointment_id"]))
            if not cancelled:
                return {
                    "intent": "cancel_appointment",
                    "pending_clarification": "",
                    "clarification_target": "",
                    "clarification_attempts": 0,
                    **_clear_pending_action_state(),
                    "messages": [AIMessage(content="这条预约当前无法取消，可能已经被处理过了。你可以再给我新的预约号或条件。")],
                }

            answer = (
                f"已为你取消预约：\n\n"
                f"- 预约号：**{cancelled['appointment_no']}**\n"
                f"- 日期：**{cancelled['date']}**\n"
                f"- 时段：**{cancelled['time_slot']}**"
            )
            return {
                "intent": "cancel_appointment",
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                "last_appointment_no": "",
                **_clear_pending_action_state(),
                "messages": [AIMessage(content=answer)],
            }

    if pending_candidates:
        if _is_abort_request(user_query):
            return {
                "intent": "cancel_appointment",
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content="好的，我先不取消了。如果你还想取消其他预约，可以继续告诉我预约号或条件。")],
            }

        selected = _pick_candidate_from_text(user_query, pending_candidates)
        if selected:
            preview_payload = {
                "appointment_id": str(selected["appointment_id"]),
                "appointment_no": selected["appointment_no"],
                "department": selected["department"],
                "date": selected["appointment_date"].isoformat(),
                "time_slot": selected["time_slot"],
                "doctor_name": selected.get("doctor_name") or "",
                "action": "cancel",
            }
            preview_payload = _with_hospital_payload(preview_payload, appointment_context)
            return {
                "intent": "cancel_appointment",
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_build_pending_confirmation("cancel_appointment", preview_payload),
                "messages": [AIMessage(content=_format_cancel_preview(preview_payload))],
            }

    llm_with_tools = llm.with_config(temperature=0.1).bind_tools([CancelActionCall])
    response = llm_with_tools.invoke(
        [
            SystemMessage(content=get_cancel_appointment_prompt()),
            HumanMessage(
                content=(
                    f"Conversation summary:\n{state.get('conversation_summary', '')}\n\n"
                    f"Last appointment number:\n{last_appointment_no}\n\n"
                    f"Existing appointment context:\n{appointment_context}\n\n"
                    f"User query:\n{user_query}"
                )
            ),
        ]
    )
    call_args = _parse_tool_call(response, "CancelActionCall")

    appointment_no = (call_args.get("appointment_no") or "").strip()
    if not appointment_no and _should_use_last_appointment(user_query):
        appointment_no = last_appointment_no
    department = (call_args.get("department") or "").strip() or appointment_context.get("department", "")
    normalized_date = _normalize_date(call_args.get("date") or appointment_context.get("date", "") or user_query)

    if call_args.get("action") == "clarify" or (not appointment_no and not (department and normalized_date)):
        clarification = (call_args.get("clarification") or "").strip() or "请告诉我要取消的预约号，或者提供科室和日期。"
        return {
            "intent": "cancel_appointment",
            "pending_clarification": clarification,
            "clarification_target": "handle_cancel_appointment",
            "clarification_attempts": _next_clarification_attempt(state),
            **_clear_pending_action_state(),
            "messages": [AIMessage(content=clarification)],
        }

    candidates = appointment_service.find_candidate_appointments(
        thread_id=state["thread_id"],
        appointment_no=appointment_no or None,
        department=department or None,
        schedule_date=date.fromisoformat(normalized_date) if normalized_date else None,
    )
    if not candidates:
        return {
            "intent": "cancel_appointment",
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
            **_clear_pending_action_state(),
            "messages": [AIMessage(content="我没有找到符合条件的可取消预约。你可以再提供预约号，或者补充科室和日期。")],
        }
    if len(candidates) > 1:
        options = "\n".join(
            f"{idx}. 预约号：{item['appointment_no']}，{item['department']}，{item['appointment_date'].isoformat()} {item['time_slot']}"
            for idx, item in enumerate(candidates[:5], start=1)
        )
        clarification = (
            "我找到了多条可取消预约，请回复具体预约号，或直接说\u201c第 1 个 / 第 2 个\u201d：\n"
            f"{options}"
        )
        return {
            "intent": "cancel_appointment",
            "pending_clarification": clarification,
            "clarification_target": "handle_cancel_appointment",
            "clarification_attempts": _next_clarification_attempt(state),
            "pending_action_type": "",
            "pending_action_payload": {},
            "pending_confirmation_id": "",
            "pending_candidates": candidates[:5],
            "messages": [AIMessage(content=clarification)],
        }

    selected = candidates[0]
    preview_payload = {
        "appointment_id": str(selected["appointment_id"]),
        "appointment_no": selected["appointment_no"],
        "department": selected["department"],
        "date": selected["appointment_date"].isoformat(),
        "time_slot": selected["time_slot"],
        "doctor_name": selected.get("doctor_name") or "",
        "action": "cancel",
    }
    return {
        "intent": "cancel_appointment",
        "pending_clarification": "",
        "clarification_target": "",
        "clarification_attempts": 0,
        **_build_pending_confirmation("cancel_appointment", preview_payload),
        "messages": [AIMessage(content=_format_cancel_preview(preview_payload))],
    }


# ---------------------------------------------------------------------------
# Appointment skill internals
# ---------------------------------------------------------------------------

def _log_appointment_skill_event(
    state: State,
    *,
    skill_mode: str,
    request_type: str,
    selected_candidate_count: int = 0,
    required_confirmation: bool = False,
    final_action: str = "",
    extra_metadata: dict | None = None,
):
    try:
        _get_appointment_skill_log_store().save_log(
            {
                "thread_id": state.get("thread_id") or "",
                "skill_mode": skill_mode,
                "request_type": request_type,
                "selected_candidate_count": selected_candidate_count,
                "required_confirmation": required_confirmation,
                "final_action": final_action,
                "extra_metadata": extra_metadata or {},
            }
        )
    except Exception:
        logger.warning("Failed to persist appointment skill log", exc_info=True)
        pass


def _invoke_appointment_skill_request(llm, state: State, user_query: str) -> dict:
    appointment_context = _get_appointment_context(state)
    # Long-term user memories (preferences, history) inform slot filling — e.g.
    # "常挂心内科" lets the parser default the department the user always books.
    user_memories_section = ""
    if state.get("user_memories"):
        user_memories_section = f"Known user context (preferences/history):\n{state['user_memories']}\n\n"
    llm_with_tools = llm.with_config(temperature=0.1).bind_tools([AppointmentSkillRequest])
    response = llm_with_tools.invoke(
        [
            SystemMessage(content=get_appointment_skill_prompt()),
            HumanMessage(
                content=(
                    f"Conversation summary:\n{state.get('conversation_summary', '')}\n\n"
                    f"{user_memories_section}"
                    f"Current intent:\n{state.get('intent') or state.get('primary_intent', '')}\n\n"
                    f"Recommended department:\n{state.get('recommended_department', '')}\n\n"
                    f"Existing appointment context:\n{appointment_context}\n\n"
                    f"Pending action type:\n{state.get('pending_action_type', '')}\n\n"
                    f"Last appointment number:\n{state.get('last_appointment_no', '')}\n\n"
                    f"User query:\n{user_query}"
                )
            ),
        ]
    )
    skill_call = _parse_tool_call(response, "AppointmentSkillRequest")
    if skill_call:
        return skill_call

    legacy_booking = _parse_tool_call(response, "AppointmentActionCall")
    if legacy_booking:
        return {
            "action": "clarify" if legacy_booking.get("action") == "clarify" else "prepare_appointment",
            "department": legacy_booking.get("department", ""),
            "date": legacy_booking.get("date", ""),
            "time_slot": legacy_booking.get("time_slot", ""),
            "doctor_name": legacy_booking.get("doctor_name", ""),
            "clarification": legacy_booking.get("clarification", ""),
        }

    legacy_cancel = _parse_tool_call(response, "CancelActionCall")
    if legacy_cancel:
        return {
            "action": "clarify" if legacy_cancel.get("action") == "clarify" else "prepare_cancellation",
            "appointment_no": legacy_cancel.get("appointment_no", ""),
            "department": legacy_cancel.get("department", ""),
            "date": legacy_cancel.get("date", ""),
            "clarification": legacy_cancel.get("clarification", ""),
        }

    return {}


def _base_skill_state_update(
    state: State,
    *,
    intent: str,
    skill_mode: str,
    topic_focus: str = "",
    appointment_context: dict | None = None,
    candidates: list[dict] | None = None,
    skill_last_prompt: str = "",
) -> dict:
    return {
        "intent": intent,
        "appointment_skill_mode": skill_mode,
        "topic_focus": topic_focus or state.get("topic_focus", ""),
        "appointment_context": _json_safe_value(appointment_context if appointment_context is not None else dict(state.get("appointment_context") or {})),
        "appointment_candidates": _json_safe_value(list(candidates or [])),
        "skill_last_prompt": skill_last_prompt or "",
    }


# ---------------------------------------------------------------------------
# MCP discovery & hospital selection helpers
# ---------------------------------------------------------------------------

def _mcp_discover_doctors(mcp, department, date=None, slot="", doctor_name=""):
    """Call MCP search_doctors → format results for display."""
    doctors, err = mcp.discover_doctors(department, date, slot)
    if err:
        return None, [], err
    items = MCPAppointmentBackend._normalise_schedule_list(doctors)
    if not items:
        return None, [], None
    # Build message
    dept_name = department or items[0].get("department_name", "")
    options = "\n".join(
        f"{i}. **{d.get('doctor_name', '')}**（剩余 {d.get('quota_available', 0)}）"
        for i, d in enumerate(items[:8], 1)
    )
    msg = f"**{dept_name}** 可预约的医生：\n\n{options}\n\n请直接回复医生姓名；如果你不挑医生，也可以回复 **任一可用医生**。"
    return msg, items, None


def _mcp_discover_schedules(mcp, department="", date=None, slot="", doctor_name=""):
    """Call MCP search_schedules → format results for display."""
    schedules, err = mcp.discover_schedules(department, date, slot, doctor_name)
    if err:
        return None, [], err
    items = MCPAppointmentBackend._normalise_schedule_list(schedules)
    if not items:
        return None, [], None
    # Sort by date and time_slot
    items = sorted(
        items,
        key=lambda s: (str(s.get("schedule_date", "")), str(s.get("time_slot", "")))
    )
    dept = department or items[0].get("department_name", "")
    lines = [f"**{dept}** 可预约时段："] if doctor_name else [f"{dept} 可选时段："]
    for i, s in enumerate(items[:8], 1):
        d = s.get("doctor_name", doctor_name)
        lines.append(f"{i}. {s.get('schedule_date','')} {s.get('time_slot','')}（{d}，余{s.get('quota_available',0)}）")
    msg = "\n".join(lines) + "\n\n你可以回复日期时段，例如 \"明天下午\"。"
    return msg, items, None


def _resolve_hospital_selection(
    state: State,
    user_query: str,
    appointment_context: dict,
    pending_payload: dict,
    *,
    mcp_pool=None,
):
    pool = mcp_pool if mcp_pool is not None else state.get("_mcp_pool")
    user_id = (state.get("user_id") or "").strip()
    if pool is None or not user_id:
        return appointment_context, None, ""

    try:
        connected = pool.get_connected_hospitals(user_id)
    except Exception:
        connected = []

    registry = getattr(pool, "_registry", None)
    hospital_lookup = getattr(registry, "get_by_code", None)
    selection_context = dict(appointment_context or {})
    if pending_payload.get("hospital_code"):
        selection_context["hospital_code"] = pending_payload.get("hospital_code", "")
    if pending_payload.get("hospital_name"):
        selection_context["hospital_name"] = pending_payload.get("hospital_name", "")

    pending_hospital_code = (selection_context.get("pending_hospital_code") or "").strip()
    pending_hospital_name = (selection_context.get("pending_hospital_name") or "").strip()
    if pending_hospital_code:
        if _is_hospital_confirmation(user_query):
            updated_context = _replace_pending_hospital(
                appointment_context,
                hospital_code=pending_hospital_code,
                hospital_name=pending_hospital_name or pending_hospital_code,
            )
            return updated_context, None, ""
        if _is_hospital_rejection(user_query):
            selection_context.pop("pending_hospital_code", None)
            selection_context.pop("pending_hospital_name", None)
        elif not _looks_like_new_hospital_choice(user_query):
            message = f"为避免挂错医院，请先确认是否使用 {pending_hospital_name or pending_hospital_code}。请回复\u201c确认医院\u201d，或直接说另一家医院。"
            return appointment_context, None, message

    selection = MCPHospitalSelectionPolicy(hospital_lookup=hospital_lookup).select(
        user_query=user_query,
        appointment_context=selection_context,
        connected_hospital_codes=connected,
    )
    if selection.needs_clarification:
        return appointment_context, selection, format_hospital_clarification(selection)
    if selection.needs_confirmation:
        updated_context = _replace_pending_hospital(
            appointment_context,
            pending_hospital_code=selection.selected_code,
            pending_hospital_name=selection.selected_name,
        )
        return updated_context, selection, format_hospital_confirmation(selection)
    if selection.selected_code:
        updated_context = _build_appointment_context(
            appointment_context,
            {
                "hospital_code": selection.selected_code,
                "hospital_name": selection.selected_name,
            },
        )
        return updated_context, selection, ""
    return appointment_context, selection, ""


def _replace_pending_hospital(
    appointment_context: dict,
    *,
    hospital_code: str = "",
    hospital_name: str = "",
    pending_hospital_code: str = "",
    pending_hospital_name: str = "",
) -> dict:
    updated = dict(appointment_context or {})
    for key in ("hospital_code", "hospital_name", "pending_hospital_code", "pending_hospital_name"):
        updated.pop(key, None)
    if hospital_code:
        updated["hospital_code"] = hospital_code
    if hospital_name:
        updated["hospital_name"] = hospital_name
    if pending_hospital_code:
        updated["pending_hospital_code"] = pending_hospital_code
    if pending_hospital_name:
        updated["pending_hospital_name"] = pending_hospital_name
    return updated


def _is_hospital_confirmation(user_query: str) -> bool:
    normalized = (user_query or "").strip().lower()
    return normalized in {"确认医院", "确认这家医院", "确认", "是", "是的", "对", "对的", "没错", "就是这家"}


def _is_hospital_rejection(user_query: str) -> bool:
    normalized = (user_query or "").strip().lower()
    return any(word in normalized for word in ("不是", "不对", "换一家", "其他医院", "别的医院", "重新选"))


def _looks_like_new_hospital_choice(user_query: str) -> bool:
    normalized = (user_query or "").strip()
    if not normalized:
        return False
    return len(normalized) <= 20


def _hospital_payload(appointment_context: dict) -> dict:
    return {
        "hospital_code": appointment_context.get("hospital_code", ""),
        "hospital_name": appointment_context.get("hospital_name", ""),
    }


def _with_hospital_payload(payload: dict, appointment_context: dict) -> dict:
    merged = dict(payload or {})
    hospital = _hospital_payload(appointment_context)
    for key, value in hospital.items():
        if value and not merged.get(key):
            merged[key] = value
    return merged
