"""Narrow-band LLM arbiter for pending-action continuation.

The rule gates handle the deterministic majority of continuation decisions.
This module is consulted ONLY when: an action is pending, the rules were
inconclusive, and the reply is short and signal-free ("行，就他了" carries no
keyword any rule can see). The verdict carries routing power only — executing
the booking still requires the explicit code gate in the appointment handler,
so a wrong "yes" costs one clarifying turn, never a wrong booking.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_ARBITER_PROMPT = (
    "你是对话状态判断器。当前有一个等待用户表态的操作：\n"
    "{summary}\n"
    "{context_section}"
    "用户刚回复：「{reply}」\n"
    "这句话是否在回应上述待办操作（同意、拒绝或修改它）？只回答「是」或「否」。"
)

_arbiter_llm = None


def _get_llm():
    """Lazy default model; kept injectable for tests via the llm parameter."""
    global _arbiter_llm
    if _arbiter_llm is None:
        from model_factory import get_chat_model
        _arbiter_llm = get_chat_model()
    return _arbiter_llm


def judge_continuation(pending_type: str, payload: dict, user_reply: str, llm=None, recent_context: str = "") -> bool:
    """Single yes/no verdict; any failure means False (fail-open to new topic).

    recent_context (the last turns) lets the model resolve referents —
    "就他了" only makes sense against the assistant's preceding question."""
    payload = payload or {}
    summary = (
        f"类型：{'预约挂号' if pending_type == 'appointment' else pending_type}；"
        f"科室：{payload.get('department', '')}；日期：{payload.get('date', '')}；"
        f"时段：{payload.get('time_slot', '')}；医生：{payload.get('doctor_name', '') or '不限'}"
    )
    context_section = ""
    trimmed_context = str(recent_context or "").strip()
    if trimmed_context:
        context_section = f"最近的对话：\n{trimmed_context[-600:]}\n"
    prompt = _ARBITER_PROMPT.format(
        summary=summary, context_section=context_section, reply=str(user_reply or "").strip(),
    )
    try:
        model = llm if llm is not None else _get_llm()
        if model is None:
            return False
        response = model.with_config(temperature=0).invoke(prompt)
        verdict = str(getattr(response, "content", "") or "").strip()
        return verdict.startswith("是") or verdict.lower().startswith("yes")
    except Exception:
        logger.debug("Continuation arbiter LLM call failed", exc_info=True)
        return False
