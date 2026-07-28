from __future__ import annotations
"""Appointment skill graph nodes.

Public entry-point wiring for booking, cancellation, rescheduling, and the
appointment-skill discovery / planning / action workflow.  Private helpers
live in ``appointment_helpers``.
"""

import logging
from datetime import date

from langchain_core.messages import AIMessage

from .graph_state import State
from services.mcp_appointment_backend import MCPAppointmentBackend

from .node_helpers import (
    _RESCHEDULE_HINTS,
    _DEPARTMENT_HINTS,
    _build_appointment_context,
    _clear_pending_action_state,
    _get_appointment_context,
    _get_pending_payload,
    _get_user_query,
    _is_abort_request,
    _is_explicit_confirmation,
    _looks_like_appointment_discovery_query,
    _next_clarification_attempt,
    _normalize_date,
    _normalize_time_slot,
    _pick_candidate_from_text,
    _should_use_last_appointment,
    _wants_any_available_doctor,
    _wants_earliest_available_slot,
)

# Re-import all private helpers from the extracted module so that existing
# callers (nodes.py, tests) can still import them from this module.
from .appointment_helpers import (  # noqa: F401
    _APPOINTMENT_SKILL_LOG_STORE,
    _get_appointment_skill_log_store,
    _pick_doctor_name_from_text,
    _sort_schedule_options,
    _find_matching_doctor_options,
    _schedule_to_preview_payload,
    _format_doctor_slot_selection_message,
    _format_doctor_options,
    _parse_tool_call,
    _build_pending_confirmation,
    _get_slot_hold_service,
    _release_slot_hold,
    _time_slot_label,
    _format_booking_preview,
    _format_cancel_preview,
    _format_reschedule_confirmation_preview,
    _handle_appointment_legacy,
    _handle_cancel_appointment_legacy,
    _log_appointment_skill_event,
    _invoke_appointment_skill_request,
    _base_skill_state_update,
    _mcp_discover_doctors,
    _mcp_discover_schedules,
    _resolve_hospital_selection,
    _replace_pending_hospital,
    _is_hospital_confirmation,
    _is_hospital_rejection,
    _looks_like_new_hospital_choice,
    _hospital_payload,
    _with_hospital_payload,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public appointment nodes
# ---------------------------------------------------------------------------

def handle_appointment_skill(state: State, llm, appointment_service, mcp_pool=None):
    _active_intent = state.get("intent") or state.get("primary_intent") or "appointment"
    # Local-DB fallback (the slot-hold path). When no MCP backend is bound for
    # this user, book/cancel against the local database instead of dead-ending
    # on "please bind a hospital". try_create returns None when MCP is disabled
    # or unbound. Reschedule stays on the MCP path (no local reschedule handler).
    if _active_intent in ("appointment", "cancel_appointment"):
        _mcp_ready = MCPAppointmentBackend.try_create(
            state, pool=mcp_pool, user_id=(state.get("user_id") or "").strip(),
        ) is not None
        if not _mcp_ready:
            if _active_intent == "cancel_appointment":
                return _handle_cancel_appointment_legacy(state, llm, appointment_service)
            return _handle_appointment_legacy(state, llm, appointment_service)
    from services.appointment_skill import AppointmentSkill
    skill = AppointmentSkill(appointment_service)
    user_query = _get_user_query(state)
    appointment_context = _get_appointment_context(state)
    pending_action_type = state.get("pending_action_type", "")
    pending_payload = _get_pending_payload(state)
    pending_candidates = state.get("pending_candidates", []) or []
    active_intent = state.get("intent") or state.get("primary_intent") or "appointment"
    appointment_context, hospital_selection, hospital_clarification = _resolve_hospital_selection(
        state,
        user_query,
        appointment_context,
        pending_payload,
        mcp_pool=mcp_pool,
    )
    selected_hospital_code = appointment_context.get("hospital_code", "")
    mcp = MCPAppointmentBackend.try_create(
        state,
        pool=mcp_pool,
        user_id=(state.get("user_id") or "").strip(),
        preferred_hospital_code=selected_hospital_code,
    )

    if hospital_clarification:
        hospital_mode = "confirm_hospital" if getattr(hospital_selection, "needs_confirmation", False) else "select_hospital"
        return {
            **_base_skill_state_update(
                state,
                intent=active_intent,
                skill_mode=hospital_mode,
                appointment_context=appointment_context,
                skill_last_prompt=hospital_clarification,
            ),
            "pending_clarification": hospital_clarification,
            "clarification_target": "handle_appointment_skill",
            "clarification_attempts": _next_clarification_attempt(state),
            "messages": [AIMessage(content=hospital_clarification)],
        }
    pending_payload = _with_hospital_payload(pending_payload, appointment_context)

    if pending_action_type == "appointment":
        if _is_abort_request(user_query):
            _log_appointment_skill_event(state, skill_mode="action", request_type="abort_booking", final_action="abort")
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="idle", topic_focus=appointment_context.get("department", state.get("topic_focus", "")), appointment_context=appointment_context),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content="好的，这次预约我先不提交了。你如果想改时间、科室或重新预约，直接告诉我即可。")],
            }
        if _is_explicit_confirmation(user_query, "appointment"):
            # Idempotency gate: if pending_confirmation_id is already empty, this
            # confirmation was already processed — refuse to double-book.
            if not state.get("pending_confirmation_id", ""):
                _log_appointment_skill_event(state, skill_mode="action", request_type="confirm_appointment_duplicate", final_action="blocked_duplicate_confirm")
                return {
                    **_base_skill_state_update(state, intent="appointment"),
                    "messages": [AIMessage(content="预约已确认完成，无需重复确认。如需改约或取消，可以直接告诉我。")],
                }
            if not mcp:
                return {
                    **_base_skill_state_update(state, intent="appointment", skill_mode="planning"),
                    "pending_clarification": "", "clarification_target": "", "clarification_attempts": 0,
                    **_clear_pending_action_state(),
                    "messages": [AIMessage(content="请先在设置中绑定医院服务，才能执行预约。")],
                }
            booking_result, mcp_err = mcp.book_appointment(pending_payload)
            if mcp_err or not booking_result:
                return {
                    **_base_skill_state_update(state, intent="appointment", skill_mode="planning", topic_focus=pending_payload.get("department", state.get("topic_focus", "")), appointment_context=appointment_context),
                    "pending_clarification": "", "clarification_target": "", "clarification_attempts": 0,
                    **_clear_pending_action_state(),
                    "messages": [AIMessage(content=mcp_err or "预约执行失败，请稍后重试。")],
                }
            booking = {
                "department": booking_result.get("department", pending_payload.get("department", "")),
                "date": booking_result.get("date", pending_payload.get("date", "")),
                "time_slot": booking_result.get("time_slot", pending_payload.get("time_slot", "")),
                "doctor_name": booking_result.get("doctor_name", pending_payload.get("doctor_name", "")),
                "appointment_no": booking_result.get("appointment_no", booking_result.get("booking_id", "")),
            }
            merged_context = _build_appointment_context(appointment_context, pending_payload)
            _log_appointment_skill_event(state, skill_mode="action", request_type="confirm_appointment", required_confirmation=True, final_action="confirm_appointment")
            if not booking:
                answer = (
                    f"刚刚确认时，**{pending_payload['department']}** 在 {pending_payload['date']} "
                    f"{pending_payload['time_slot']} 的号源已经不可用了。你可以换个日期、时段，或让我继续帮你改约。"
                )
                return {
                    **_base_skill_state_update(state, intent="appointment", skill_mode="planning", topic_focus=merged_context.get("department", state.get("topic_focus", "")), appointment_context=merged_context),
                    "pending_clarification": "",
                    "clarification_target": "",
                    "clarification_attempts": 0,
                    **_clear_pending_action_state(),
                    "messages": [AIMessage(content=answer)],
                }
            answer = (
                f"已为你预约成功：\n\n"
                f"- 科室：**{booking['department']}**\n"
                f"- 日期：**{booking['date']}**\n"
                f"- 时段：**{booking['time_slot']}**\n"
                f"- 医生：**{booking['doctor_name']}**\n"
                f"- 预约号：**{booking['appointment_no']}**"
            )
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="completed", topic_focus=merged_context.get("department", state.get("topic_focus", "")), appointment_context=merged_context),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                "last_appointment_no": booking["appointment_no"],
                **_clear_pending_action_state(),
                "messages": [AIMessage(content=answer)],
            }
        if not _looks_like_appointment_discovery_query(user_query):
            return {
                **_base_skill_state_update(
                    state,
                    intent="appointment",
                    skill_mode="prepare_appointment",
                    topic_focus=appointment_context.get("department", state.get("topic_focus", "")),
                    appointment_context=appointment_context,
                ),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_build_pending_confirmation("appointment", pending_payload),
                "messages": [AIMessage(content="如果你确认这条预约，请直接回复 **确认预约**；如果想改时间、医生或科室，也可以直接告诉我。")],
            }

    if pending_action_type == "cancel_appointment":
        if _is_abort_request(user_query):
            _log_appointment_skill_event(state, skill_mode="action", request_type="abort_cancellation", final_action="abort")
            return {
                **_base_skill_state_update(state, intent="cancel_appointment", skill_mode="idle"),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content="好的，这次取消我先不提交了。如果你想取消其他预约，直接告诉我预约号或条件即可。")],
            }
        if _is_explicit_confirmation(user_query, "cancel_appointment"):
            if not mcp:
                return {
                    **_base_skill_state_update(state, intent="cancel_appointment", skill_mode="planning"),
                    "pending_clarification": "", "clarification_target": "", "clarification_attempts": 0,
                    **_clear_pending_action_state(),
                    "messages": [AIMessage(content="请先在设置中绑定医院服务，才能取消预约。")],
                }
            cancel_result, mcp_err = mcp.cancel_appointment(pending_payload)
            if mcp_err or not cancel_result:
                return {
                    **_base_skill_state_update(state, intent="cancel_appointment", skill_mode="planning"),
                    "pending_clarification": "", "clarification_target": "", "clarification_attempts": 0,
                    **_clear_pending_action_state(),
                    "messages": [AIMessage(content=mcp_err or "取消执行失败，请稍后重试。")],
                }
            cancelled = {
                "appointment_no": cancel_result.get("appointment_no", pending_payload.get("appointment_no", "")),
                "date": cancel_result.get("date", pending_payload.get("date", "")),
                "time_slot": cancel_result.get("time_slot", pending_payload.get("time_slot", "")),
            }
            _log_appointment_skill_event(state, skill_mode="action", request_type="confirm_cancellation", required_confirmation=True, final_action="confirm_cancellation")
            if not cancelled:
                return {
                    **_base_skill_state_update(state, intent="cancel_appointment", skill_mode="planning"),
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
                **_base_skill_state_update(state, intent="cancel_appointment", skill_mode="completed"),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                "last_appointment_no": "",
                **_clear_pending_action_state(),
                "messages": [AIMessage(content=answer)],
            }
        if not _should_use_last_appointment(user_query):
            return {
                **_base_skill_state_update(state, intent="cancel_appointment", skill_mode="prepare_cancellation"),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_build_pending_confirmation("cancel_appointment", pending_payload),
                "messages": [AIMessage(content="如果你确认取消这条预约，请直接回复 **确认取消**；如果想取消别的预约，也可以直接告诉我预约号或说\u201c第 1 个 / 第 2 个\u201d。")],
            }

    if pending_action_type == "reschedule_appointment":
        if _is_abort_request(user_query):
            _log_appointment_skill_event(state, skill_mode="action", request_type="abort_reschedule", final_action="abort")
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="idle", topic_focus=appointment_context.get("department", state.get("topic_focus", "")), appointment_context=appointment_context),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content="好的，这次改约我先不提交了。你如果想继续改时间、时段或医生，直接告诉我即可。")],
            }
        if _is_explicit_confirmation(user_query, "reschedule_appointment"):
            rescheduled = skill.confirm_reschedule(state["thread_id"], pending_payload)
            _log_appointment_skill_event(state, skill_mode="action", request_type="confirm_reschedule", required_confirmation=True, final_action="confirm_reschedule")
            if not rescheduled:
                return {
                    **_base_skill_state_update(state, intent="appointment", skill_mode="planning", topic_focus=appointment_context.get("department", state.get("topic_focus", "")), appointment_context=appointment_context),
                    "pending_clarification": "",
                    "clarification_target": "",
                    "clarification_attempts": 0,
                    **_clear_pending_action_state(),
                    "messages": [AIMessage(content="刚刚确认改约时，新时段已经不可用了。你可以换一个日期、时段，或者让我重新帮你找可改约的医生。")],
                }
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="completed", topic_focus=rescheduled.get("department", state.get("topic_focus", "")), appointment_context=_build_appointment_context(appointment_context, {"department": rescheduled.get("department", ""), "date": rescheduled.get("date", ""), "time_slot": rescheduled.get("time_slot", ""), "doctor_name": rescheduled.get("doctor_name", "")})),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                "last_appointment_no": rescheduled["appointment_no"],
                **_clear_pending_action_state(),
                "messages": [
                    AIMessage(
                        content=(
                            "已为你改约成功：\n\n"
                            f"- 预约号：**{rescheduled['appointment_no']}**\n"
                            f"- 原预约：**{rescheduled['previous_department']}**，**{rescheduled['previous_date']}**，**{rescheduled['previous_time_slot']}**\n"
                            f"- 新预约：**{rescheduled['department']}**，**{rescheduled['date']}**，**{rescheduled['time_slot']}**\n"
                            f"- 医生：**{rescheduled['doctor_name']}**"
                        )
                    )
                ],
            }
        return {
            **_base_skill_state_update(state, intent="appointment", skill_mode="prepare_reschedule", topic_focus=appointment_context.get("department", state.get("topic_focus", "")), appointment_context=appointment_context),
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
            **_build_pending_confirmation("reschedule_appointment", pending_payload),
            "messages": [AIMessage(content="如果你确认这次改约，请直接回复 **确认预约**；如果想换成别的日期、时段或医生，也可以直接告诉我。")],
        }

    if pending_candidates and active_intent == "cancel_appointment":
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
            _log_appointment_skill_event(state, skill_mode="planning", request_type="select_cancellation_candidate", selected_candidate_count=len(pending_candidates), required_confirmation=True, final_action="prepare_cancellation")
            return {
                **_base_skill_state_update(state, intent="cancel_appointment", skill_mode="planning", candidates=[], skill_last_prompt=_format_cancel_preview(preview_payload)),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_build_pending_confirmation("cancel_appointment", preview_payload),
                "messages": [AIMessage(content=_format_cancel_preview(preview_payload))],
            }
        return {
            **_base_skill_state_update(state, intent="cancel_appointment", skill_mode="list_my_appointments", candidates=pending_candidates),
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
            "pending_candidates": pending_candidates,
            "messages": [AIMessage(content="我还没确定你要取消哪一条。你可以直接回复预约号，或者说\u201c第 1 个 / 第 2 个\u201d。")],
        }

    available_doctors = list(appointment_context.get("available_doctors") or [])
    selected_doctor_name = _pick_doctor_name_from_text(user_query, available_doctors) or appointment_context.get("doctor_name", "")
    if active_intent == "appointment" and available_doctors:
        if _wants_any_available_doctor(user_query):
            chosen_schedule = _sort_schedule_options(available_doctors)[0]
            payload = _schedule_to_preview_payload(chosen_schedule)
            payload = _with_hospital_payload(payload, appointment_context)
            preview_message = _format_booking_preview(payload)
            _log_appointment_skill_event(
                state,
                skill_mode="planning",
                request_type="prepare_appointment",
                selected_candidate_count=len(available_doctors),
                required_confirmation=True,
                final_action="prepare_any_available_doctor",
            )
            return {
                **_base_skill_state_update(
                    state,
                    intent="appointment",
                    skill_mode="prepare_appointment",
                    topic_focus=payload["department"],
                    appointment_context=_build_appointment_context(
                        appointment_context,
                        {
                            "department": payload["department"],
                            "date": payload["date"],
                            "time_slot": payload["time_slot"],
                            "doctor_name": payload["doctor_name"],
                            "available_doctors": available_doctors,
                        },
                    ),
                    candidates=available_doctors,
                    skill_last_prompt=preview_message,
                ),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_build_pending_confirmation("appointment", payload),
                "messages": [AIMessage(content=preview_message)],
            }
        matching_doctor_options = _find_matching_doctor_options(available_doctors, selected_doctor_name)
        if matching_doctor_options:
            if len(matching_doctor_options) == 1 or _wants_earliest_available_slot(user_query):
                chosen_schedule = _sort_schedule_options(matching_doctor_options)[0]
                payload = _schedule_to_preview_payload(chosen_schedule)
                payload = _with_hospital_payload(payload, appointment_context)
                preview_message = _format_booking_preview(payload)
                _log_appointment_skill_event(
                    state,
                    skill_mode="planning",
                    request_type="prepare_appointment",
                    selected_candidate_count=len(matching_doctor_options),
                    required_confirmation=True,
                    final_action="prepare_selected_doctor",
                )
                return {
                    **_base_skill_state_update(
                        state,
                        intent="appointment",
                        skill_mode="prepare_appointment",
                        topic_focus=payload["department"],
                        appointment_context=_build_appointment_context(
                            appointment_context,
                            {
                                "department": payload["department"],
                                "date": payload["date"],
                                "time_slot": payload["time_slot"],
                                "doctor_name": payload["doctor_name"],
                                "available_doctors": matching_doctor_options,
                            },
                        ),
                        candidates=matching_doctor_options,
                        skill_last_prompt=preview_message,
                    ),
                    "pending_clarification": "",
                    "clarification_target": "",
                    "clarification_attempts": 0,
                    **_build_pending_confirmation("appointment", payload),
                    "messages": [AIMessage(content=preview_message)],
                }
            selection_message = _format_doctor_slot_selection_message(
                appointment_context.get("department", "") or matching_doctor_options[0].get("department_name", ""),
                selected_doctor_name,
                matching_doctor_options,
            )
            _log_appointment_skill_event(
                state,
                skill_mode="discovery",
                request_type="discover_availability",
                selected_candidate_count=len(matching_doctor_options),
                final_action="discover_selected_doctor_slots",
            )
            return {
                **_base_skill_state_update(
                    state,
                    intent="appointment",
                    skill_mode="discover_availability",
                    topic_focus=appointment_context.get("department", "") or selected_doctor_name,
                    appointment_context=_build_appointment_context(
                        appointment_context,
                        {"available_doctors": matching_doctor_options, "doctor_name": selected_doctor_name},
                    ),
                    candidates=matching_doctor_options,
                    skill_last_prompt=selection_message,
                ),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content=selection_message)],
            }

    call_args = _invoke_appointment_skill_request(llm, state, user_query)
    department = (call_args.get("department") or "").strip() or state.get("recommended_department", "") or appointment_context.get("department", "")
    # Rule-based department extraction fallback: if the LLM tool call didn't
    # extract a department, scan the raw user query for known department names.
    # This must run BEFORE any skill_action early-return (e.g. "clarify") so
    # that "帮我挂一个皮肤科的号" correctly picks up 皮肤科 even when the LLM
    # returns action=clarify (because it couldn't determine date/time).
    if not department:
        for dep_name in _DEPARTMENT_HINTS:
            if dep_name in user_query:
                department = dep_name
                break
    normalized_date = _normalize_date(call_args.get("date") or appointment_context.get("date", "") or user_query)
    time_slot = _normalize_time_slot(call_args.get("time_slot") or appointment_context.get("time_slot", "") or user_query)
    appointment_no = (call_args.get("appointment_no") or "").strip()
    doctor_name = (
        (call_args.get("doctor_name") or "").strip()
        or _pick_doctor_name_from_text(user_query, appointment_context.get("available_doctors") or [])
        or appointment_context.get("doctor_name", "")
    )
    skill_action = (call_args.get("action") or "").strip() or ("prepare_cancellation" if active_intent == "cancel_appointment" else "prepare_appointment")
    wants_any_doctor = _wants_any_available_doctor(user_query)
    merged_context = _build_appointment_context(
        appointment_context,
        {"department": department, "date": normalized_date, "time_slot": time_slot, "doctor_name": doctor_name},
    )
    available_doctors = list(appointment_context.get("available_doctors") or [])
    matching_doctor_options = _find_matching_doctor_options(available_doctors, doctor_name)

    if active_intent == "appointment" and available_doctors and not normalized_date and not time_slot:
        if wants_any_doctor:
            chosen_schedule = _sort_schedule_options(available_doctors)[0]
            payload = _schedule_to_preview_payload(chosen_schedule)
            payload = _with_hospital_payload(payload, merged_context)
            preview_message = _format_booking_preview(payload)
            _log_appointment_skill_event(
                state,
                skill_mode="planning",
                request_type="prepare_appointment",
                selected_candidate_count=len(available_doctors),
                required_confirmation=True,
                final_action="prepare_any_available_doctor",
            )
            return {
                **_base_skill_state_update(
                    state,
                    intent="appointment",
                    skill_mode="prepare_appointment",
                    topic_focus=payload["department"],
                    appointment_context=_build_appointment_context(
                        merged_context,
                        {
                            "department": payload["department"],
                            "date": payload["date"],
                            "time_slot": payload["time_slot"],
                            "doctor_name": payload["doctor_name"],
                            "available_doctors": available_doctors,
                        },
                    ),
                    candidates=available_doctors,
                    skill_last_prompt=preview_message,
                ),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_build_pending_confirmation("appointment", payload),
                "messages": [AIMessage(content=preview_message)],
            }
        if matching_doctor_options:
            if len(matching_doctor_options) == 1 or _wants_earliest_available_slot(user_query):
                chosen_schedule = _sort_schedule_options(matching_doctor_options)[0]
                payload = _schedule_to_preview_payload(chosen_schedule)
                payload = _with_hospital_payload(payload, merged_context)
                preview_message = _format_booking_preview(payload)
                _log_appointment_skill_event(
                    state,
                    skill_mode="planning",
                    request_type="prepare_appointment",
                    selected_candidate_count=len(matching_doctor_options),
                    required_confirmation=True,
                    final_action="prepare_selected_doctor",
                )
                return {
                    **_base_skill_state_update(
                        state,
                        intent="appointment",
                        skill_mode="prepare_appointment",
                        topic_focus=payload["department"],
                        appointment_context=_build_appointment_context(
                            merged_context,
                            {
                                "department": payload["department"],
                                "date": payload["date"],
                                "time_slot": payload["time_slot"],
                                "doctor_name": payload["doctor_name"],
                                "available_doctors": matching_doctor_options,
                            },
                        ),
                        candidates=matching_doctor_options,
                        skill_last_prompt=preview_message,
                    ),
                    "pending_clarification": "",
                    "clarification_target": "",
                    "clarification_attempts": 0,
                    **_build_pending_confirmation("appointment", payload),
                    "messages": [AIMessage(content=preview_message)],
                }
            selection_message = _format_doctor_slot_selection_message(
                department or matching_doctor_options[0].get("department_name", ""),
                doctor_name,
                matching_doctor_options,
            )
            _log_appointment_skill_event(
                state,
                skill_mode="discovery",
                request_type="discover_availability",
                selected_candidate_count=len(matching_doctor_options),
                final_action="discover_selected_doctor_slots",
            )
            return {
                **_base_skill_state_update(
                    state,
                    intent="appointment",
                    skill_mode="discover_availability",
                    topic_focus=department or doctor_name,
                    appointment_context=_build_appointment_context(
                        merged_context,
                        {"available_doctors": matching_doctor_options, "doctor_name": doctor_name},
                    ),
                    candidates=matching_doctor_options,
                    skill_last_prompt=selection_message,
                ),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content=selection_message)],
            }

    if skill_action == "clarify":
        clarification = (call_args.get("clarification") or "").strip() or "你可以再补充一下要处理的预约信息。"
        _log_appointment_skill_event(state, skill_mode="clarify", request_type=active_intent, final_action="clarify")
        return {
            **_base_skill_state_update(state, intent=active_intent, skill_mode="clarify", topic_focus=department or state.get("topic_focus", ""), appointment_context=merged_context, skill_last_prompt=clarification),
            "pending_clarification": clarification,
            "clarification_target": "handle_appointment_skill",
            "clarification_attempts": _next_clarification_attempt(state),
            **_clear_pending_action_state(),
            "messages": [AIMessage(content=clarification)],
        }

    if skill_action == "discover_department":
        message = skill.discover_departments(department or user_query)
        _log_appointment_skill_event(state, skill_mode="discovery", request_type="discover_department", final_action="discover_department")
        return {
            **_base_skill_state_update(state, intent="appointment", skill_mode="discover_department", appointment_context=merged_context, skill_last_prompt=message),
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
            **_clear_pending_action_state(),
            "messages": [AIMessage(content=message)],
        }

    if skill_action == "list_my_appointments" or (active_intent == "cancel_appointment" and not appointment_no and not department and not normalized_date):
        if not mcp:
            return {
                **_base_skill_state_update(state, intent=active_intent, skill_mode="list_my_appointments", skill_last_prompt=""),
                "messages": [AIMessage(content="请先在设置中绑定医院服务，才能查看预约。")],
            }
        raw, mcp_err = mcp.list_appointments()
        if mcp_err:
            message = mcp_err
            appointments = []
        else:
            appointments = MCPAppointmentBackend._normalise_schedule_list(raw)
            if appointments:
                lines = ["你当前有以下预约："] + [
                    f"{i}. {a.get('appointment_no','')} — {a.get('department','')} {a.get('date','')} {a.get('time_slot','')}"
                    for i, a in enumerate(appointments[:8], 1)
                ]
                message = "\n".join(lines)
            else:
                message = "你当前没有预约记录。"
        _log_appointment_skill_event(state, skill_mode="discovery", request_type="list_my_appointments", selected_candidate_count=len(appointments), final_action="list_my_appointments")
        return {
            **_base_skill_state_update(state, intent=active_intent, skill_mode="list_my_appointments", candidates=appointments, skill_last_prompt=message),
            "pending_clarification": message if active_intent == "cancel_appointment" and appointments else "",
            "clarification_target": "handle_appointment_skill" if active_intent == "cancel_appointment" and appointments else "",
            "clarification_attempts": int(state.get("clarification_attempts") or 0) + (1 if active_intent == "cancel_appointment" and appointments else 0),
            "pending_candidates": appointments[:8] if active_intent == "cancel_appointment" else [],
            "messages": [AIMessage(content=message)],
        }

    if skill_action == "discover_doctor":
        if not department:
            clarification = "你想先看哪个科室的医生？如果还不确定，我也可以先根据症状帮你推荐科室。"
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="clarify", appointment_context=merged_context, skill_last_prompt=clarification),
                "pending_clarification": clarification,
                "clarification_target": "handle_appointment_skill",
                "clarification_attempts": _next_clarification_attempt(state),
                "messages": [AIMessage(content=clarification)],
            }
        schedule_date_value = date.fromisoformat(normalized_date) if normalized_date and time_slot else None
        if not mcp:
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="discover_doctor", topic_focus=department, appointment_context=merged_context,
                skill_last_prompt=""), "pending_clarification": "", "clarification_target": "", "clarification_attempts": 0,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content="请先在设置中绑定医院服务，才能查询医生。")],
            }
        message, doctor_options, mcp_err = _mcp_discover_doctors(mcp, department, schedule_date_value, time_slot)
        if mcp_err:
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="discover_doctor", topic_focus=department, appointment_context=merged_context, skill_last_prompt=mcp_err),
                "pending_clarification": "", "clarification_target": "", "clarification_attempts": 0,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content=mcp_err)],
            }
        _log_appointment_skill_event(state, skill_mode="discovery", request_type="discover_doctor", selected_candidate_count=len(doctor_options), final_action="discover_doctor")
        return {
            **_base_skill_state_update(state, intent="appointment", skill_mode="discover_doctor", topic_focus=department, appointment_context=_build_appointment_context(merged_context, {"available_doctors": doctor_options}), candidates=doctor_options, skill_last_prompt=message),
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
            **_clear_pending_action_state(),
            "messages": [AIMessage(content=message)],
        }

    if skill_action == "discover_availability":
        if not mcp:
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="discover_availability", topic_focus=department or doctor_name, appointment_context=merged_context,
                skill_last_prompt=""), "pending_clarification": "", "clarification_target": "", "clarification_attempts": 0,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content="请先在设置中绑定医院服务，才能查询号源。")],
            }
        schedule_date_value = date.fromisoformat(normalized_date) if normalized_date else None
        m_msg, availability, mcp_err = _mcp_discover_schedules(mcp, department, schedule_date_value, time_slot, doctor_name)
        if mcp_err:
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="discover_availability", topic_focus=department or doctor_name, appointment_context=merged_context, skill_last_prompt=mcp_err),
                "pending_clarification": "", "clarification_target": "", "clarification_attempts": 0,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content=mcp_err)],
            }
        _log_appointment_skill_event(state, skill_mode="discovery", request_type="discover_availability", selected_candidate_count=len(availability), final_action="discover_availability")
        return {
            **_base_skill_state_update(state, intent="appointment", skill_mode="discover_availability", topic_focus=department or doctor_name, appointment_context=_build_appointment_context(merged_context, {"available_doctors": availability}), candidates=availability, skill_last_prompt=m_msg),
            "pending_clarification": "", "clarification_target": "", "clarification_attempts": 0,
            **_clear_pending_action_state(),
            "messages": [AIMessage(content=m_msg)],
        }

    if skill_action == "prepare_reschedule" or any(token in (user_query or "").lower() for token in _RESCHEDULE_HINTS):
        current_items = appointment_service.find_candidate_appointments(
            thread_id=state["thread_id"],
            appointment_no=appointment_no or (state.get("last_appointment_no", "") if _should_use_last_appointment(user_query) else "") or None,
            department=department or None,
            schedule_date=date.fromisoformat(normalized_date) if normalized_date else None,
        )
        if not current_items:
            message = "我暂时没锁定要改约的那条预约。你可以先告诉我预约号，或者说\u201c改最近那个预约\u201d。"
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="clarify", appointment_context=merged_context, skill_last_prompt=message),
                "pending_clarification": message,
                "clarification_target": "handle_appointment_skill",
                "clarification_attempts": _next_clarification_attempt(state),
                "messages": [AIMessage(content=message)],
            }
        if not normalized_date or not time_slot:
            message = skill.prepare_reschedule(
                state["thread_id"],
                current_items[0],
                target_date=date.fromisoformat(normalized_date) if normalized_date else None,
                time_slot=time_slot,
            )
            _log_appointment_skill_event(state, skill_mode="planning", request_type="prepare_reschedule", selected_candidate_count=1, final_action="prepare_reschedule_options")
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="prepare_reschedule", topic_focus=current_items[0]["department"], appointment_context=merged_context, candidates=current_items, skill_last_prompt=message),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content=message)],
            }
        preview, doctor_options, alternatives = skill.prepare_reschedule_preview(
            candidate=current_items[0],
            target_date=date.fromisoformat(normalized_date),
            time_slot=time_slot,
            doctor_name=doctor_name,
            allow_any_doctor=wants_any_doctor,
        )
        if preview:
            payload = preview.__dict__
            payload = _with_hospital_payload(payload, merged_context)
            _log_appointment_skill_event(state, skill_mode="planning", request_type="prepare_reschedule", selected_candidate_count=len(doctor_options), required_confirmation=True, final_action="prepare_reschedule")
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="prepare_reschedule", topic_focus=payload["department"], appointment_context=_build_appointment_context(merged_context, {"department": payload["department"], "date": payload["date"], "time_slot": payload["time_slot"], "doctor_name": payload.get("doctor_name", "")}), candidates=doctor_options, skill_last_prompt=_format_reschedule_confirmation_preview(payload)),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_build_pending_confirmation("reschedule_appointment", payload),
                "messages": [AIMessage(content=_format_reschedule_confirmation_preview(payload))],
            }
        if doctor_options:
            message, doctor_options = skill.discover_doctors(current_items[0]["department"], schedule_date=date.fromisoformat(normalized_date), time_slot=time_slot)
            _log_appointment_skill_event(state, skill_mode="discovery", request_type="discover_doctor", selected_candidate_count=len(doctor_options), final_action="discover_reschedule_doctor")
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="discover_doctor", topic_focus=current_items[0]["department"], appointment_context=_build_appointment_context(merged_context, {"available_doctors": doctor_options, "doctor_name": ""}), candidates=doctor_options, skill_last_prompt=message),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content=message)],
            }
        if alternatives:
            message = "当前目标时段没有合适的可改约号源，我找到这些替代选择：\n\n" + "\n".join(
                f"- **{item['doctor_name']}**：{item['schedule_date']} {item['time_slot']}（剩余号源 {item.get('quota_available', 0)}）"
                for item in alternatives[:6]
            )
            _log_appointment_skill_event(state, skill_mode="discovery", request_type="prepare_reschedule", selected_candidate_count=len(alternatives), final_action="discover_reschedule_alternatives")
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="discover_availability", topic_focus=current_items[0]["department"], appointment_context=merged_context, candidates=alternatives, skill_last_prompt=message),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content=message)],
            }
        message = "暂时没有找到可改约的新号源。你可以换一个日期、时段，或者让我继续找其他医生。"
        return {
            **_base_skill_state_update(state, intent="appointment", skill_mode="discover_availability", topic_focus=current_items[0]["department"], appointment_context=merged_context, skill_last_prompt=message),
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
            **_clear_pending_action_state(),
            "messages": [AIMessage(content=message)],
        }

    if active_intent == "cancel_appointment" or skill_action in {"prepare_cancellation", "confirm_cancellation"}:
        if not appointment_no and _should_use_last_appointment(user_query):
            appointment_no = state.get("last_appointment_no", "")
        if not mcp:
            return {
                **_base_skill_state_update(state, intent="cancel_appointment", skill_mode="prepare_cancellation", skill_last_prompt=""),
                "pending_clarification": "", "clarification_target": "", "clarification_attempts": 0,
                "messages": [AIMessage(content="请先在设置中绑定医院服务，才能取消预约。")],
            }
        raw, mcp_err = mcp.list_appointments()
        if mcp_err:
            preview = None
            candidates = []
        else:
            all_appts = MCPAppointmentBackend._normalise_schedule_list(raw)
            candidates = [
                a for a in all_appts
                if (not appointment_no or a.get("appointment_no") == appointment_no)
                and (not department or department in str(a.get("department", "")))
            ]
            preview = candidates[0] if len(candidates) == 1 else None
        if preview:
            payload = preview.__dict__
            payload = _with_hospital_payload(payload, merged_context)
            _log_appointment_skill_event(state, skill_mode="planning", request_type="prepare_cancellation", required_confirmation=True, final_action="prepare_cancellation")
            return {
                **_base_skill_state_update(state, intent="cancel_appointment", skill_mode="prepare_cancellation", topic_focus=payload["department"], appointment_context=merged_context, skill_last_prompt=_format_cancel_preview(payload)),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_build_pending_confirmation("cancel_appointment", payload),
                "messages": [AIMessage(content=_format_cancel_preview(payload))],
            }
        message = "我没有找到符合条件的可取消预约。你可以再提供预约号，或者补充科室和日期。"
        if candidates:
            message = "我找到了多条可取消预约，请回复具体预约号，或直接说\u201c第 1 个 / 第 2 个\u201d：\n" + "\n".join(
                f"{idx}. 预约号：{item['appointment_no']}，{item['department']}，{item['appointment_date'].isoformat()} {item['time_slot']}"
                for idx, item in enumerate(candidates[:8], start=1)
            )
        _log_appointment_skill_event(state, skill_mode="discovery", request_type="prepare_cancellation", selected_candidate_count=len(candidates), final_action="list_cancellation_candidates")
        return {
            **_base_skill_state_update(state, intent="cancel_appointment", skill_mode="list_my_appointments", candidates=candidates, skill_last_prompt=message),
            "pending_clarification": message if candidates else "",
            "clarification_target": "handle_appointment_skill" if candidates else "",
            "clarification_attempts": int(state.get("clarification_attempts") or 0) + (1 if candidates else 0),
            **_clear_pending_action_state(),
            "pending_candidates": candidates[:8],
            "messages": [AIMessage(content=message)],
        }

    # Rule-based department extraction fallback: scan the user query for known
    # department names when the structured parsers above didn't find one.
    if not department:
        user_query = state.get("primary_user_query", "") or (
            state.get("recent_context", [""])[-1] if state.get("recent_context") else ""
        )
        for dep_name in _DEPARTMENT_HINTS:
            if dep_name in user_query:
                department = dep_name
                merged_context = _build_appointment_context(
                    merged_context, {"department": department}
                )
                break

    if not department:
        clarification = "你想挂哪个科室？如果还不确定，我也可以先根据症状帮你推荐挂什么科。"
        return {
            **_base_skill_state_update(state, intent="appointment", skill_mode="clarify", appointment_context=merged_context, skill_last_prompt=clarification),
            "pending_clarification": clarification,
            "clarification_target": "handle_appointment_skill",
            "clarification_attempts": _next_clarification_attempt(state),
            **_clear_pending_action_state(),
            "messages": [AIMessage(content=clarification)],
        }

    if not normalized_date or not time_slot:
        if not mcp:
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="discover_availability", topic_focus=department, appointment_context=merged_context,
                skill_last_prompt=""), "pending_clarification": "", "clarification_target": "", "clarification_attempts": 0,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content="请先在设置中绑定医院服务，才能查询号源。")],
            }
        sched_msg, upcoming, sched_err = _mcp_discover_schedules(mcp, department, date.fromisoformat(normalized_date), time_slot, doctor_name)
        if sched_err:
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="discover_availability", topic_focus=department, appointment_context=merged_context, skill_last_prompt=sched_err),
                "pending_clarification": "", "clarification_target": "", "clarification_attempts": 0,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content=sched_err)],
            }
        _log_appointment_skill_event(state, skill_mode="discovery", request_type="discover_availability", selected_candidate_count=len(upcoming), final_action="discover_availability")
        return {
            **_base_skill_state_update(state, intent="appointment", skill_mode="discover_availability", topic_focus=department, appointment_context=_build_appointment_context(merged_context, {"available_doctors": upcoming}), candidates=upcoming, skill_last_prompt=sched_msg),
            "pending_clarification": "", "clarification_target": "", "clarification_attempts": 0,
            **_clear_pending_action_state(),
            "messages": [AIMessage(content=sched_msg)],
        }

    if not mcp:
        return {
            **_base_skill_state_update(state, intent="appointment", skill_mode="planning"), "pending_clarification": "",
            "clarification_target": "", "clarification_attempts": 0,
            "messages": [AIMessage(content="请先在设置中绑定医院服务，才能预约。")],
        }
    sched_msg, schedules, sched_err = _mcp_discover_schedules(mcp, department, date.fromisoformat(normalized_date), time_slot, doctor_name)
    if sched_err:
        preview = None; doctor_options = []; alternatives = []
    elif schedules:
        first = schedules[0]
        preview = type("_Preview", (), {"__dict__": {
            "department": first.get("department_name", department),
            "date": str(first.get("schedule_date", normalized_date)),
            "time_slot": first.get("time_slot", time_slot),
            "doctor_name": first.get("doctor_name", doctor_name),
            "action": "book",
        }})()
        doctor_options = schedules
        alternatives = []
    else:
        preview = None; doctor_options = []; alternatives = []
    if preview:
        payload = preview.__dict__
        payload = _with_hospital_payload(payload, merged_context)
        _log_appointment_skill_event(state, skill_mode="planning", request_type="prepare_appointment", selected_candidate_count=len(doctor_options), required_confirmation=True, final_action="prepare_appointment")
        return {
            **_base_skill_state_update(state, intent="appointment", skill_mode="prepare_appointment", topic_focus=payload["department"], appointment_context=_build_appointment_context(merged_context, {"available_doctors": doctor_options, "doctor_name": payload.get("doctor_name", "")}), candidates=doctor_options, skill_last_prompt=_format_booking_preview(payload)),
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
            **_build_pending_confirmation("appointment", payload),
            "messages": [AIMessage(content=_format_booking_preview(payload))],
        }
    if doctor_options:
        message, doctor_options = skill.discover_doctors(department, schedule_date=date.fromisoformat(normalized_date), time_slot=time_slot)
        _log_appointment_skill_event(state, skill_mode="discovery", request_type="discover_doctor", selected_candidate_count=len(doctor_options), final_action="discover_doctor")
        return {
            **_base_skill_state_update(state, intent="appointment", skill_mode="discover_doctor", topic_focus=department, appointment_context=_build_appointment_context(merged_context, {"available_doctors": doctor_options, "doctor_name": ""}), candidates=doctor_options, skill_last_prompt=message),
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
            **_clear_pending_action_state(),
            "messages": [AIMessage(content=message)],
        }
    if alternatives:
        message = "当前指定医生或时段没有可用号源，我找到这些替代选择：\n\n" + "\n".join(
            f"- **{item['doctor_name']}**：{item['schedule_date']} {item['time_slot']}（剩余号源 {item.get('quota_available', 0)}）"
            for item in alternatives[:6]
        )
        _log_appointment_skill_event(state, skill_mode="discovery", request_type="discover_alternatives", selected_candidate_count=len(alternatives), final_action="discover_alternatives")
        return {
            **_base_skill_state_update(state, intent="appointment", skill_mode="discover_availability", topic_focus=department, appointment_context=merged_context, candidates=alternatives, skill_last_prompt=message),
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
            **_clear_pending_action_state(),
            "messages": [AIMessage(content=message)],
        }

    message = f"暂时没有找到 **{department}** 在 {normalized_date} {time_slot} 的可预约号源。你可以换一个日期、时间段，或继续让我帮你找其他医生。"
    _log_appointment_skill_event(state, skill_mode="discovery", request_type="prepare_appointment", final_action="no_availability")
    return {
        **_base_skill_state_update(state, intent="appointment", skill_mode="discover_availability", topic_focus=department, appointment_context=merged_context, skill_last_prompt=message),
        "pending_clarification": "",
        "clarification_target": "",
        "clarification_attempts": 0,
        **_clear_pending_action_state(),
        "messages": [AIMessage(content=message)],
    }


def handle_appointment(state: State, llm, appointment_service, mcp_pool=None):
    merged_state = dict(state)
    merged_state.setdefault("intent", "appointment")
    merged_state.setdefault("primary_intent", "appointment")
    return handle_appointment_skill(merged_state, llm, appointment_service, mcp_pool=mcp_pool)


def handle_cancel_appointment(state: State, llm, appointment_service, mcp_pool=None):
    merged_state = dict(state)
    merged_state.setdefault("intent", "cancel_appointment")
    merged_state.setdefault("primary_intent", "cancel_appointment")
    return handle_appointment_skill(merged_state, llm, appointment_service, mcp_pool=mcp_pool)


__all__ = [
    "handle_appointment",
    "handle_appointment_skill",
    "handle_cancel_appointment",
    "_handle_appointment_legacy",
    "_handle_cancel_appointment_legacy",
    "_log_appointment_skill_event",
    "_invoke_appointment_skill_request",
    "_base_skill_state_update",
    "_build_pending_confirmation",
    "_format_booking_preview",
    "_format_cancel_preview",
    "_format_reschedule_confirmation_preview",
    "_format_doctor_options",
    "_format_doctor_slot_selection_message",
    "_parse_tool_call",
    "_pick_doctor_name_from_text",
    "_sort_schedule_options",
    "_find_matching_doctor_options",
    "_schedule_to_preview_payload",
    "_get_appointment_skill_log_store",
]
