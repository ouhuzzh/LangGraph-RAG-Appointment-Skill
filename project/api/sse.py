import logging
import json
import re
from typing import Iterable, List

from api.dependencies import get_container
from api.schemas import ChatSseEvent


logger = logging.getLogger(__name__)


def event_payload(event: ChatSseEvent) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


def _detect_card_events(content: str, thread_id: str) -> List[str]:
    """Heuristic detection of structured UI cards from the final assistant text.

    Emits 'ui-card' SSE events for department recommendations, risk alerts,
    and appointment previews.  Returns formatted SSE event strings."""
    events = []
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
    # Appointment preview card
    if "预约" in content and ("确认" in content or "预览" in content):
        card = {"card_type": "appointment_preview"}
        events.append(event_payload(ChatSseEvent(
            type="ui-card", thread_id=thread_id, content=json.dumps(card, ensure_ascii=False),
        )))
    return events


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


def stream_chat_events(thread_id: str, message: str) -> Iterable[str]:
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
        for chunk in container.chat_interface.chat(
            message,
            [],
            reveal_diagnostics=False,
            thread_id=thread_id,
        ):
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
        # Generative UI: emit structured card events from the final content
        for card_event_str in _detect_card_events(final_content, thread_id):
            yield card_event_str
        yield event_payload(ChatSseEvent(type="final", thread_id=thread_id, content=final_content, done=True))
    finally:
        if acquired and lock is not None:
            lock.release()
