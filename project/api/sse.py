import asyncio
import logging
import json
import re
from typing import Iterable, List

from api.dependencies import get_container
from api.schemas import ChatSseEvent


logger = logging.getLogger(__name__)


def event_payload(event: ChatSseEvent) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


def _detect_card_events(content: str, thread_id: str, session_state: dict | None = None) -> List[str]:
    """Heuristic detection of structured UI cards from the final assistant text.

    Emits 'ui-card' SSE events for department recommendations, risk alerts,
    and appointment previews.  Returns formatted SSE event strings."""
    events = []
    state = session_state or {}
    # Department recommendation card
    dept_match = re.search(r"\*\*([^*]*科[^*]*)\*\*", content)
    if dept_match and ("建议" in content or "科室" in content):
        card = {"card_type": "department", "department": dept_match.group(1).strip()}
        events.append(event_payload(ChatSseEvent(
            type="ui-card", thread_id=thread_id, content=json.dumps(card, ensure_ascii=False),
        )))
    # Emergency/risk alert card
    if "紧急提醒" in content or "风险提醒" in content:
        level = "critical" if "紧急提醒" in content else "high"
        card = {"card_type": "risk_alert", "level": level}
        events.append(event_payload(ChatSseEvent(
            type="ui-card", thread_id=thread_id, content=json.dumps(card, ensure_ascii=False),
        )))
    # Appointment preview card — when a confirmation is actually pending, ship
    # structured actions so the client can confirm via button instead of free
    # text (the confirmation_id equality check replaces keyword parsing).
    if "预约" in content and ("确认" in content or "预览" in content):
        card = {"card_type": "appointment_preview"}
        confirmation_id = str(state.get("pending_confirmation_id") or "")
        if confirmation_id and state.get("pending_action_type") == "appointment":
            payload = state.get("pending_action_payload") or {}
            _slot = str(payload.get("time_slot") or "")
            _slot_label = {"morning": "上午", "afternoon": "下午", "evening": "晚间", "night": "晚间"}.get(_slot.strip().lower(), _slot)
            card["details"] = {
                "department": str(payload.get("department") or ""),
                "date": str(payload.get("date") or ""),
                "time_slot": _slot_label,
                "doctor_name": str(payload.get("doctor_name") or ""),
            }
            card["actions"] = [
                {"label": "确认预约", "action": "confirm_appointment", "confirmation_id": confirmation_id},
                {"label": "暂不预约", "action": "abort_appointment", "confirmation_id": confirmation_id},
            ]
        events.append(event_payload(ChatSseEvent(
            type="ui-card", thread_id=thread_id, content=json.dumps(card, ensure_ascii=False),
        )))
    return events


# Structured actions map button clicks to canonical command texts that the
# rule gates match deterministically. The confirmation_id equality check below
# is the real gate — free-text keyword parsing is bypassed entirely.
_ACTION_CANONICAL_MESSAGES = {
    "confirm_appointment": "确认预约",
    "abort_appointment": "算了，先不预约了",
}


def _session_state_for_thread(container, thread_id: str) -> dict:
    try:
        return container.chat_interface.rag_system.session_memory.get_state(thread_id) or {}
    except Exception:
        logger.warning("Failed to load session state for card enrichment", exc_info=True)
        return {}


def resolve_structured_action(container, thread_id: str, action: dict) -> tuple[str, str]:
    """Validate a button action against the pending confirmation state.

    Returns (canonical_message, "") on success or ("", error_text) when the
    action is unknown or the confirmation has expired/been superseded."""
    action_type = str((action or {}).get("type") or "")
    canonical = _ACTION_CANONICAL_MESSAGES.get(action_type)
    if not canonical:
        return "", "无法识别的操作，请直接输入文字继续。"
    supplied_id = str((action or {}).get("confirmation_id") or "")
    pending_id = str(_session_state_for_thread(container, thread_id).get("pending_confirmation_id") or "")
    if not pending_id or supplied_id != pending_id:
        return "", "该确认已过期或已处理，请重新发起预约。"
    return canonical, ""


def stream_action_rejected(thread_id: str, reason: str) -> Iterable[str]:
    """Short SSE stream for a rejected structured action (expired/unknown)."""
    yield event_payload(ChatSseEvent(type="session", thread_id=thread_id, content=thread_id))
    yield event_payload(ChatSseEvent(type="final", thread_id=thread_id, content=reason, done=True))


def visible_assistant_text(chunk) -> str:
    if isinstance(chunk, str):
        return chunk.strip()
    if not isinstance(chunk, list):
        return ""
    for item in reversed(chunk):
        if not isinstance(item, dict):
            continue
        if item.get("role") != "assistant":
            continue
        content = str(item.get("content") or "").strip()
        if content:
            return content
    return ""


async def stream_chat_events(thread_id: str, message: str) -> Iterable[str]:
    """Async generator for SSE streaming.

    Runs the synchronous chat generator in a thread pool so the event loop
    is never blocked by LLM / retrieval calls.
    """
    container = get_container()
    final_content = ""
    yield event_payload(ChatSseEvent(type="session", thread_id=thread_id, content=thread_id))
    yield event_payload(ChatSseEvent(type="status", thread_id=thread_id, content="thinking"))
    lock = None
    acquired = False
    try:
        lock = container.get_thread_lock(thread_id)
        acquired = lock.acquire(timeout=120)
        if not acquired:
            yield event_payload(
                ChatSseEvent(
                    type="app-error",
                    thread_id=thread_id,
                    content="会话繁忙，请稍后再试。",
                    error="thread_lock_timeout",
                    done=True,
                )
            )
            return

        # Run the sync generator in a thread pool to avoid blocking the event loop.
        def _collect_sync():
            results = []
            gen = container.chat_interface.chat(
                message,
                [],
                reveal_diagnostics=False,
                thread_id=thread_id,
            )
            try:
                for chunk in gen:
                    results.append(chunk)
            except Exception:
                logger.exception("Sync chat generator failed for thread_id=%s", thread_id)
                raise
            return results

        try:
            chunks = await asyncio.to_thread(_collect_sync)
        except Exception as exc:
            yield event_payload(
                ChatSseEvent(
                    type="app-error",
                    thread_id=thread_id,
                    content="聊天服务暂时不可用，请稍后再试。",
                    error=str(exc),
                    done=True,
                )
            )
            return

        for chunk in chunks:
            content = visible_assistant_text(chunk)
            if not content:
                continue
            final_content = content
            yield event_payload(ChatSseEvent(type="message", thread_id=thread_id, content=content))
    except Exception as exc:
        logger.exception("API chat stream failed for thread_id=%s", thread_id)
        yield event_payload(
            ChatSseEvent(
                type="app-error",
                thread_id=thread_id,
                content="聊天服务暂时不可用，请稍后再试。",
                error=str(exc),
                done=True,
            )
        )
    else:
        # Generative UI: emit structured card events from the final content,
        # enriched with pending-confirmation state so cards can carry actions.
        try:
            session_state = _session_state_for_thread(container, thread_id)
            for card_event_str in _detect_card_events(final_content, thread_id, session_state):
                yield card_event_str
            yield event_payload(ChatSseEvent(type="final", thread_id=thread_id, content=final_content, done=True))
        except Exception:
            logger.exception("Failed to emit final/card events")
            yield event_payload(ChatSseEvent(
                type="final", thread_id=thread_id, content=final_content, done=True,
            ))
    finally:
        if acquired and lock is not None:
            lock.release()
