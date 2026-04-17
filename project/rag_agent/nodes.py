import re
import uuid
from typing import Literal, Set
from datetime import date, timedelta
from langchain_core.messages import SystemMessage, HumanMessage, RemoveMessage, AIMessage, ToolMessage
from langgraph.types import Command
from .graph_state import State, AgentState
from .schemas import (
    QueryAnalysis,
    IntentAnalysis,
    DepartmentRecommendation,
    AppointmentActionCall,
    CancelActionCall,
)
from .prompts import *
from utils import estimate_context_tokens
from config import BASE_TOKEN_THRESHOLD, TOKEN_GROWTH_FACTOR, HIGH_RISK_KEYWORDS

_TIME_RE = re.compile(r"(\d{1,2})[:：点时]")
_YEAR_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?")
_MONTH_DAY_RE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?")
_SLASH_DATE_RE = re.compile(r"(\d{4})[/.](\d{1,2})[/.](\d{1,2})")
_WEEKDAY_RE = re.compile(r"(下|这|本)?\s*周([一二三四五六日天])")
_ORDINAL_RE = re.compile(r"第\s*([1-9]\d*)\s*(个|条)?")
_APPOINTMENT_NO_RE = re.compile(r"\bAPT[A-Z0-9]+\b", re.IGNORECASE)
_CN_HOUR_MAP = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    "十": 10, "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15, "十六": 16,
    "十七": 17, "十八": 18, "十九": 19, "二十": 20, "二十一": 21, "二十二": 22, "二十三": 23,
}
_CN_HOUR_RE = re.compile(r"(二十三|二十二|二十一|二十|十九|十八|十七|十六|十五|十四|十三|十二|十一|十|[一二三四五六七八九])")
_APPOINTMENT_CONFIRM_WORDS = (
    "确认预约", "确认挂号", "确认就诊", "确认预订", "请预约", "帮我预约", "现在预约", "立即预约", "确认",
)
_CANCEL_CONFIRM_WORDS = (
    "确认取消", "确认退号", "确定取消", "现在取消", "立即取消", "确认",
)
_ABORT_WORDS = (
    "先不用", "先不", "不用了", "算了", "取消这个操作", "放弃", "暂不", "不预约了", "不取消了",
)
_MEDICAL_FOLLOW_UP_HINTS = (
    "那", "这个", "这种情况", "这会", "还会", "严重吗", "怎么办", "注意什么", "要紧吗",
    "what about", "does that", "is that", "should i", "what should",
)


def _clear_pending_action_state() -> dict:
    return {
        "pending_action_type": "",
        "pending_action_payload": {},
        "pending_confirmation_id": "",
        "pending_candidates": [],
    }


def _reset_pending_action_if_needed(state: State) -> dict:
    if not state.get("pending_action_type") and not state.get("pending_candidates"):
        return {}
    return _clear_pending_action_state()


def _looks_like_greeting(query: str) -> bool:
    normalized = (query or "").strip().lower()
    greetings = [
        "你好", "您好", "hello", "hi", "hey", "嗨", "哈喽",
        "早上好", "下午好", "晚上好", "good morning", "good afternoon", "good evening",
        "谢谢", "感谢", "thanks", "thank you", "thx",
        "再见", "拜拜", "bye", "goodbye",
    ]
    # 短消息且完全匹配问候语
    if len(normalized) <= 15 and any(g in normalized for g in greetings):
        return True
    return False


def _looks_like_department_question(query: str) -> bool:
    """Check if the query looks like a department recommendation question."""
    normalized = (query or "").strip().lower()
    patterns = [
        "挂什么科",
        "挂哪个科",
        "看什么科",
        "看哪个科",
        "挂哪科",
        "看哪科",
        "咨询什么科",
        "consult which department",
        "which department",
        "what department should i visit",
        "what department should i register for",
    ]
    return any(pattern in normalized for pattern in patterns)


def _looks_like_medical_knowledge_question(query: str) -> bool:
    normalized = (query or "").strip().lower()
    if not normalized or _looks_like_department_question(normalized):
        return False

    medical_terms = [
        "高血压", "糖尿病", "感冒", "发烧", "头晕", "咳嗽", "腹痛", "胃痛", "胸闷", "胸痛",
        "呼吸困难", "肺炎", "哮喘", "鼻炎", "胃炎", "肠胃炎", "失眠", "焦虑", "抑郁",
        "血压", "血糖", "检查", "药", "症状", "疾病", "炎", "癌", "病",
        "hypertension", "diabetes", "fever", "cough", "dizziness", "headache", "pneumonia",
        "asthma", "symptom", "treatment", "disease", "medicine", "blood pressure",
    ]
    question_patterns = [
        "是什么", "怎么回事", "为什么", "原因", "症状", "表现", "怎么办", "如何", "怎么处理",
        "怎么缓解", "严重吗", "会不会", "会引起", "会导致", "能不能", "可以吗", "要不要",
        "是否", "注意事项", "治疗", "预防", "means", "what is", "why", "how to", "symptoms",
        "treatment", "can ", "could ", "does ", "is it",
    ]

    has_medical_term = any(term in normalized for term in medical_terms)
    has_question_pattern = any(pattern in normalized for pattern in question_patterns) or normalized.endswith("?") or normalized.endswith("？")
    return has_medical_term and has_question_pattern


def _normalize_time_slot(raw_value: str) -> str:
    normalized = (raw_value or "").strip().lower()
    if not normalized:
        return ""
    context_evening = ["晚上", "傍晚", "evening", "night", "晚间", "今晚"]
    context_afternoon = ["下午", "afternoon", "午后", "中午", "中午后"]
    context_morning = ["上午", "早上", "早晨", "morning", "清晨"]
    if any(token in normalized for token in context_evening):
        return "evening"
    if any(token in normalized for token in context_afternoon):
        return "afternoon"
    if any(token in normalized for token in context_morning):
        return "morning"

    hour_match = _TIME_RE.search(normalized)
    cn_hour_match = _CN_HOUR_RE.search(normalized)
    has_half = "半" in normalized or ":30" in normalized or "：30" in normalized
    hour = None
    if hour_match:
        try:
            hour = int(hour_match.group(1))
        except ValueError:
            pass
    elif cn_hour_match:
        hour = _CN_HOUR_MAP.get(cn_hour_match.group(1))
    if hour is not None:
        if hour >= 18 or (hour == 12 and has_half):
            return "evening"
        if hour >= 12:
            return "afternoon"
        return "morning"
    # 兜底: am/pm 标识
    if "am" in normalized:
        return "morning"
    if "pm" in normalized:
        return "afternoon"
    return ""


def _normalize_date(raw_value: str) -> str:
    normalized = (raw_value or "").strip().lower()
    if not normalized:
        return ""
    today = date.today()
    if "今天" in normalized or "today" in normalized:
        return today.isoformat()
    if "明天" in normalized or "tomorrow" in normalized:
        return (today + timedelta(days=1)).isoformat()
    if "后天" in normalized or "day after tomorrow" in normalized:
        return (today + timedelta(days=2)).isoformat()
    if "这个周末" in normalized or "本周末" in normalized:
        return (today + timedelta(days=(5 - today.weekday()) % 7)).isoformat()
    if "下周末" in normalized:
        return (today + timedelta(days=((5 - today.weekday()) % 7) + 7)).isoformat()

    if len(normalized) == 10 and normalized[4] == "-" and normalized[7] == "-":
        try:
            return date.fromisoformat(normalized).isoformat()
        except ValueError:
            return ""

    weekday_match = _WEEKDAY_RE.search(normalized)
    if weekday_match:
        prefix = weekday_match.group(1) or ""
        weekday_text = weekday_match.group(2)
        target_weekday = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}[weekday_text]
        delta = (target_weekday - today.weekday()) % 7
        if prefix == "下" or (not prefix and delta == 0 and "下" in normalized):
            delta += 7
        return (today + timedelta(days=delta)).isoformat()

    m = _YEAR_DATE_RE.search(normalized)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return ""

    m = _MONTH_DAY_RE.search(normalized)
    if m:
        try:
            candidate = date(today.year, int(m.group(1)), int(m.group(2)))
            if candidate < today:
                candidate = date(today.year + 1, int(m.group(1)), int(m.group(2)))
            return candidate.isoformat()
        except ValueError:
            return ""

    m = _SLASH_DATE_RE.search(normalized)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return ""
    return ""


def _build_appointment_context(existing: dict | None, updates: dict) -> dict:
    context = dict(existing or {})
    for key, value in updates.items():
        if value:
            context[key] = value
    return context


def _sanitize_pending_payload(payload: dict | None) -> dict:
    cleaned = dict(payload or {})
    for key in ("department", "date", "time_slot", "doctor_name", "appointment_no", "action"):
        value = cleaned.get(key)
        if isinstance(value, str):
            cleaned[key] = value.strip()
    return cleaned


def _parse_tool_call(response, expected_name: str) -> dict:
    tool_calls = getattr(response, "tool_calls", None) or []
    for tool_call in tool_calls:
        if tool_call.get("name") == expected_name:
            return tool_call.get("args") or {}
    return {}


def _is_explicit_confirmation(user_query: str, pending_action_type: str) -> bool:
    normalized = (user_query or "").strip().lower()
    if not normalized:
        return False
    if pending_action_type == "appointment":
        return any(word in normalized for word in _APPOINTMENT_CONFIRM_WORDS)
    if pending_action_type == "cancel_appointment":
        return any(word in normalized for word in _CANCEL_CONFIRM_WORDS)
    return False


def _is_abort_request(user_query: str) -> bool:
    normalized = (user_query or "").strip().lower()
    return any(word in normalized for word in _ABORT_WORDS)


def _pick_candidate_from_text(user_query: str, pending_candidates: list[dict]) -> dict | None:
    if not pending_candidates:
        return None

    match = _APPOINTMENT_NO_RE.search(user_query or "")
    if match:
        appointment_no = match.group(0).upper()
        for item in pending_candidates:
            if str(item.get("appointment_no", "")).upper() == appointment_no:
                return item

    ordinal = _ORDINAL_RE.search(user_query or "")
    if ordinal:
        index = int(ordinal.group(1)) - 1
        if 0 <= index < len(pending_candidates):
            return pending_candidates[index]
    return None


def _should_use_last_appointment(user_query: str) -> bool:
    normalized = (user_query or "").strip().lower()
    hints = ("刚刚", "刚才", "上一个", "上一条", "那个预约", "这个预约", "这条预约")
    return any(token in normalized for token in hints)


def _looks_like_medical_follow_up(user_query: str, conversation_summary: str) -> bool:
    normalized = (user_query or "").strip().lower()
    if not normalized or not conversation_summary.strip():
        return False
    return any(token in normalized for token in _MEDICAL_FOLLOW_UP_HINTS)


def _looks_like_appointment_update(user_query: str) -> bool:
    normalized = (user_query or "").strip().lower()
    if any(keyword in normalized for keyword in ("挂号", "预约", "改到", "换到", "改成", "换成", "医生", "科", "时间", "时段")):
        return True
    return bool(_normalize_date(user_query) or _normalize_time_slot(user_query))


def _looks_like_cancel_update(user_query: str) -> bool:
    normalized = (user_query or "").strip().lower()
    if any(keyword in normalized for keyword in ("取消", "退号", "预约号", "appointment", "cancel")):
        return True
    return bool(_APPOINTMENT_NO_RE.search(user_query or "") or _ORDINAL_RE.search(user_query or ""))


def _should_continue_pending_action(state: State, user_query: str) -> bool:
    pending_action_type = state.get("pending_action_type", "")
    pending_candidates = state.get("pending_candidates", []) or []
    if not pending_action_type and not pending_candidates:
        return False
    if _is_explicit_confirmation(user_query, pending_action_type) or _is_abort_request(user_query):
        return True
    if pending_candidates and _pick_candidate_from_text(user_query, pending_candidates):
        return True
    if pending_action_type == "appointment":
        return _looks_like_appointment_update(user_query)
    if pending_action_type == "cancel_appointment":
        return _looks_like_cancel_update(user_query)
    return False


def _build_pending_confirmation(action_type: str, payload: dict) -> dict:
    return {
        "pending_action_type": action_type,
        "pending_action_payload": _sanitize_pending_payload(payload),
        "pending_confirmation_id": uuid.uuid4().hex,
        "pending_candidates": [],
    }


def _format_booking_preview(payload: dict) -> str:
    doctor_name = payload.get("doctor_name") or "不限"
    return (
        "我已经整理好预约信息，请回复 **确认预约** 来正式提交：\n\n"
        f"- 科室：**{payload['department']}**\n"
        f"- 日期：**{payload['date']}**\n"
        f"- 时段：**{payload['time_slot']}**\n"
        f"- 医生：**{doctor_name}**\n\n"
        "如果你想改日期、时段、科室或医生，直接告诉我新的要求即可。"
    )


def _format_cancel_preview(payload: dict) -> str:
    return (
        "我已找到要取消的预约，请回复 **确认取消** 来正式提交：\n\n"
        f"- 预约号：**{payload['appointment_no']}**\n"
        f"- 科室：**{payload['department']}**\n"
        f"- 日期：**{payload['date']}**\n"
        f"- 时段：**{payload['time_slot']}**\n\n"
        "如果你想换一条预约取消，也可以直接告诉我新的预约号或条件。"
    )


def summarize_history(state: State, llm):
    existing_summary = state.get("conversation_summary", "")
    if len(state["messages"]) < 4:
        return {"conversation_summary": existing_summary}
    
    relevant_msgs = [
        msg for msg in state["messages"][:-1]
        if isinstance(msg, (HumanMessage, AIMessage)) and not getattr(msg, "tool_calls", None)
    ]

    if not relevant_msgs:
        return {"conversation_summary": existing_summary}
    
    conversation = "Conversation history:\n"
    if existing_summary.strip():
        conversation += f"[Prior conversation summary]\n{existing_summary}\n\n"
    for msg in relevant_msgs[-6:]:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        conversation += f"{role}: {msg.content}\n"

    summary_response = llm.with_config(temperature=0.2).invoke([SystemMessage(content=get_conversation_summary_prompt()), HumanMessage(content=conversation)])
    return {"conversation_summary": summary_response.content, "agent_answers": [{"__reset__": True}]}


def _infer_risk_level(user_query: str, existing_risk: str = "normal") -> str:
    normalized = (user_query or "").strip().lower()
    if any(keyword.lower() in normalized for keyword in HIGH_RISK_KEYWORDS):
        return "high"
    return existing_risk or "normal"


def intent_router(state: State, llm):
    last_message = state["messages"][-1]
    user_query = str(last_message.content).strip()
    normalized_query = user_query.lower()
    risk_level = _infer_risk_level(user_query, state.get("risk_level", "normal"))
    pending_action_type = state.get("pending_action_type", "")
    pending_candidates = state.get("pending_candidates", []) or []

    if pending_action_type and _should_continue_pending_action(state, user_query):
        return {
            "intent": pending_action_type,
            "risk_level": risk_level,
            "pending_clarification": "",
            "clarification_target": "",
            "recommended_department": state.get("recommended_department", ""),
            "appointment_context": state.get("appointment_context", {}),
            "last_appointment_no": state.get("last_appointment_no", ""),
            "pending_action_type": pending_action_type,
            "pending_action_payload": state.get("pending_action_payload", {}),
            "pending_confirmation_id": state.get("pending_confirmation_id", ""),
            "pending_candidates": pending_candidates,
        }

    if pending_candidates and _pick_candidate_from_text(user_query, pending_candidates):
        return {
            "intent": "cancel_appointment",
            "risk_level": risk_level,
            "pending_clarification": "",
            "clarification_target": "",
            "recommended_department": state.get("recommended_department", ""),
            "appointment_context": state.get("appointment_context", {}),
            "last_appointment_no": state.get("last_appointment_no", ""),
            "pending_action_type": state.get("pending_action_type", ""),
            "pending_action_payload": state.get("pending_action_payload", {}),
            "pending_confirmation_id": state.get("pending_confirmation_id", ""),
            "pending_candidates": pending_candidates,
        }

    if _looks_like_greeting(user_query):
        greeting_response = "你好！我是你的医疗助手，可以帮你：\n- 🏥 推荐就诊科室\n- 📅 预约挂号\n- ❌ 取消预约\n- 💊 解答医疗健康问题\n\n请问有什么可以帮你的？"
        return {
            "intent": "greeting",
            "risk_level": risk_level,
            "pending_clarification": "",
            "clarification_target": "",
            "recommended_department": state.get("recommended_department", ""),
            "appointment_context": state.get("appointment_context", {}),
            "last_appointment_no": state.get("last_appointment_no", ""),
            **_reset_pending_action_if_needed(state),
            "messages": [AIMessage(content=greeting_response)],
        }

    if _looks_like_department_question(user_query):
        return {
            "intent": "triage",
            "risk_level": risk_level,
            "pending_clarification": "",
            "clarification_target": "",
            "recommended_department": "",
            "appointment_context": {},
            "last_appointment_no": "",
            **_clear_pending_action_state(),
        }

    has_appointment_keyword = any(keyword in normalized_query for keyword in ["挂号", "预约", "book appointment", "register"])
    has_cancel_keyword = any(keyword in normalized_query for keyword in ["取消", "退号", "cancel appointment", "cancel booking"])

    # 复合意图: "取消+挂号" → 优先走预约(用户最终目的是挂号)
    if has_appointment_keyword:
        return {
            "intent": "appointment",
            "risk_level": risk_level,
            "pending_clarification": "",
            "clarification_target": "",
            "recommended_department": state.get("recommended_department", ""),
            "appointment_context": state.get("appointment_context", {}),
            "last_appointment_no": state.get("last_appointment_no", ""),
            "pending_action_type": state.get("pending_action_type", ""),
            "pending_action_payload": state.get("pending_action_payload", {}),
            "pending_confirmation_id": state.get("pending_confirmation_id", ""),
            "pending_candidates": state.get("pending_candidates", []),
        }

    if has_cancel_keyword:
        return {
            "intent": "cancel_appointment",
            "risk_level": risk_level,
            "pending_clarification": "",
            "clarification_target": "",
            "recommended_department": state.get("recommended_department", ""),
            "appointment_context": state.get("appointment_context", {}),
            "last_appointment_no": state.get("last_appointment_no", ""),
            "pending_action_type": state.get("pending_action_type", ""),
            "pending_action_payload": state.get("pending_action_payload", {}),
            "pending_confirmation_id": state.get("pending_confirmation_id", ""),
            "pending_candidates": state.get("pending_candidates", []),
        }

    llm_with_structure = llm.with_config(temperature=0.1).with_structured_output(IntentAnalysis)
    response = llm_with_structure.invoke(
        [
            SystemMessage(content=get_intent_router_prompt()),
            HumanMessage(content=f"Conversation summary:\n{state.get('conversation_summary', '')}\n\nUser query:\n{user_query}"),
        ]
    )

    if response.is_clear and response.intent in {"medical_rag", "triage", "appointment", "cancel_appointment"}:
        pending_updates = (
            _clear_pending_action_state()
            if response.intent in {"medical_rag", "triage"}
            else {
                "pending_action_type": state.get("pending_action_type", ""),
                "pending_action_payload": state.get("pending_action_payload", {}),
                "pending_confirmation_id": state.get("pending_confirmation_id", ""),
                "pending_candidates": state.get("pending_candidates", []),
            }
        )
        return {
            "intent": response.intent,
            "risk_level": risk_level,
            "pending_clarification": "",
            "clarification_target": "",
            "recommended_department": state.get("recommended_department", ""),
            "appointment_context": state.get("appointment_context", {}),
            "last_appointment_no": state.get("last_appointment_no", ""),
            **pending_updates,
        }

    if _looks_like_medical_knowledge_question(user_query) or _looks_like_medical_follow_up(user_query, state.get("conversation_summary", "")):
        return {
            "intent": "medical_rag",
            "risk_level": risk_level,
            "pending_clarification": "",
            "clarification_target": "",
            "recommended_department": state.get("recommended_department", ""),
            "appointment_context": state.get("appointment_context", {}),
            "last_appointment_no": state.get("last_appointment_no", ""),
            **_reset_pending_action_if_needed(state),
        }

    clarification = response.clarification_needed if response.clarification_needed and len(response.clarification_needed.strip()) > 5 else "可以再具体描述一下你的问题吗？"
    return {
        "intent": "clarification",
        "risk_level": risk_level,
        "pending_clarification": clarification,
        "clarification_target": "intent_router",
        "recommended_department": state.get("recommended_department", ""),
        "appointment_context": state.get("appointment_context", {}),
        "last_appointment_no": state.get("last_appointment_no", ""),
        **_reset_pending_action_if_needed(state),
        "messages": [AIMessage(content=clarification)],
    }


def rewrite_query(state: State, llm):
    last_message = state["messages"][-1]
    conversation_summary = state.get("conversation_summary", "")
    user_query = str(last_message.content).strip()

    context_section = (f"Conversation Context:\n{conversation_summary}\n" if conversation_summary.strip() else "") + f"User Query:\n{user_query}\n"

    llm_with_structure = llm.with_config(temperature=0.1).with_structured_output(QueryAnalysis)
    response = llm_with_structure.invoke([SystemMessage(content=get_rewrite_query_prompt()), HumanMessage(content=context_section)])

    if response.questions and response.is_clear:
        delete_all = [RemoveMessage(id=m.id) for m in state["messages"] if not isinstance(m, SystemMessage)]
        return {
            "questionIsClear": True,
            "messages": delete_all,
            "originalQuery": user_query,
            "rewrittenQuestions": response.questions,
            "pending_clarification": "",
            "clarification_target": "",
        }

    if _looks_like_department_question(user_query):
        delete_all = [RemoveMessage(id=m.id) for m in state["messages"] if not isinstance(m, SystemMessage)]
        return {
            "questionIsClear": True,
            "messages": delete_all,
            "originalQuery": user_query,
            "rewrittenQuestions": [user_query],
            "pending_clarification": "",
            "clarification_target": "",
        }

    if state.get("intent") == "medical_rag" and _looks_like_medical_knowledge_question(user_query):
        delete_all = [RemoveMessage(id=m.id) for m in state["messages"] if not isinstance(m, SystemMessage)]
        fallback_query = response.questions[0] if response.questions else user_query
        return {
            "questionIsClear": True,
            "messages": delete_all,
            "originalQuery": user_query,
            "rewrittenQuestions": [fallback_query],
            "pending_clarification": "",
            "clarification_target": "",
        }

    if state.get("intent") == "medical_rag" and _looks_like_medical_follow_up(user_query, conversation_summary):
        delete_all = [RemoveMessage(id=m.id) for m in state["messages"] if not isinstance(m, SystemMessage)]
        fallback_query = response.questions[0] if response.questions else f"{conversation_summary}\nFollow-up: {user_query}"
        return {
            "questionIsClear": True,
            "messages": delete_all,
            "originalQuery": user_query,
            "rewrittenQuestions": [fallback_query],
            "pending_clarification": "",
            "clarification_target": "",
        }

    clarification = response.clarification_needed if response.clarification_needed and len(response.clarification_needed.strip()) > 10 else "我可以继续帮你，但还差一点关键信息。你能再具体一点吗？"
    return {
        "questionIsClear": False,
        "pending_clarification": clarification,
        "clarification_target": "rewrite_query",
        "messages": [AIMessage(content=clarification)],
    }


def recommend_department(state: State, llm):
    last_message = state["messages"][-1]
    user_query = str(last_message.content).strip()
    conversation_summary = state.get("conversation_summary", "")
    risk_level = state.get("risk_level", "normal")

    llm_with_structure = llm.with_config(temperature=0.1).with_structured_output(DepartmentRecommendation)
    response = llm_with_structure.invoke(
        [
            SystemMessage(content=get_department_recommendation_prompt()),
            HumanMessage(content=f"Conversation summary:\n{conversation_summary}\n\nUser query:\n{user_query}"),
        ]
    )

    if response.needs_clarification or not response.department.strip():
        if risk_level == "high":
            answer = "你描述里有较高风险信号，建议优先去 **急诊科** 进一步评估；如果症状明显加重，请立即线下就医。"
            return {
                "pending_clarification": "",
                "clarification_target": "",
                "recommended_department": "急诊科",
                "appointment_context": _build_appointment_context(state.get("appointment_context"), {"department": "急诊科"}),
                **_reset_pending_action_if_needed(state),
                "messages": [AIMessage(content=answer)],
            }
        clarification = response.clarification_needed if response.clarification_needed and len(response.clarification_needed.strip()) > 5 else "可以再补充一下你的主要症状、持续时间或最不舒服的部位吗？"
        return {
            "pending_clarification": clarification,
            "clarification_target": "recommend_department",
            "recommended_department": "",
            **_reset_pending_action_if_needed(state),
            "messages": [AIMessage(content=clarification)],
        }

    answer = f"建议优先咨询 **{response.department.strip()}**。\n\n原因：{response.reason.strip()}"
    if risk_level == "high":
        answer += "\n\n你当前描述里有较高风险信号，建议尽快线下就医；如果症状明显加重，请优先考虑急诊评估。"

    return {
        "recommended_department": response.department.strip(),
        "pending_clarification": "",
        "clarification_target": "",
        "appointment_context": _build_appointment_context(state.get("appointment_context"), {"department": response.department.strip()}),
        **_clear_pending_action_state(),
        "messages": [AIMessage(content=answer)],
    }


def handle_appointment(state: State, llm, appointment_service):
    last_message = state["messages"][-1]
    user_query = str(last_message.content).strip()
    appointment_context = dict(state.get("appointment_context") or {})
    pending_action_type = state.get("pending_action_type", "")
    pending_payload = _sanitize_pending_payload(state.get("pending_action_payload"))

    if pending_action_type == "appointment":
        if _is_abort_request(user_query):
            return {
                "intent": "appointment",
                "pending_clarification": "",
                "clarification_target": "",
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
                    "appointment_context": merged_context,
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
                "intent": "appointment",
                "pending_clarification": "",
                "clarification_target": "",
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
    doctor_name = (call_args.get("doctor_name") or "").strip() or appointment_context.get("doctor_name", "")

    merged_context = _build_appointment_context(
        appointment_context,
        {
            "department": department,
            "date": normalized_date,
            "time_slot": time_slot,
            "doctor_name": doctor_name,
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
            "appointment_context": merged_context,
            **_clear_pending_action_state(),
            "messages": [AIMessage(content=clarification)],
        }

    schedule = appointment_service.find_available_schedule(
        department=department,
        schedule_date=date.fromisoformat(normalized_date),
        time_slot=time_slot,
        doctor_name=doctor_name or None,
    )
    if not schedule:
        answer = f"暂时没有找到 **{department}** 在 {normalized_date} {time_slot} 的可预约号源。你可以换一个日期、时间段，或继续让我帮你改约。"
        return {
            "intent": "appointment",
            "pending_clarification": "",
            "clarification_target": "",
            "appointment_context": merged_context,
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
        "appointment_context": merged_context,
        **_build_pending_confirmation("appointment", preview_payload),
        "messages": [AIMessage(content=_format_booking_preview(preview_payload))],
    }


def handle_cancel_appointment(state: State, llm, appointment_service):
    last_message = state["messages"][-1]
    user_query = str(last_message.content).strip()
    appointment_context = dict(state.get("appointment_context") or {})
    last_appointment_no = state.get("last_appointment_no", "")
    pending_action_type = state.get("pending_action_type", "")
    pending_payload = _sanitize_pending_payload(state.get("pending_action_payload"))
    pending_candidates = state.get("pending_candidates", []) or []

    if pending_action_type == "cancel_appointment":
        if _is_abort_request(user_query):
            return {
                "intent": "cancel_appointment",
                "pending_clarification": "",
                "clarification_target": "",
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
            return {
                "intent": "cancel_appointment",
                "pending_clarification": "",
                "clarification_target": "",
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
            **_clear_pending_action_state(),
            "messages": [AIMessage(content="我没有找到符合条件的可取消预约。你可以再提供预约号，或者补充科室和日期。")],
        }
    if len(candidates) > 1:
        options = "\n".join(
            f"{idx}. 预约号：{item['appointment_no']}，{item['department']}，{item['appointment_date'].isoformat()} {item['time_slot']}"
            for idx, item in enumerate(candidates[:5], start=1)
        )
        clarification = (
            "我找到了多条可取消预约，请回复具体预约号，或直接说“第 1 个 / 第 2 个”：\n"
            f"{options}"
        )
        return {
            "intent": "cancel_appointment",
            "pending_clarification": clarification,
            "clarification_target": "handle_cancel_appointment",
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
        **_build_pending_confirmation("cancel_appointment", preview_payload),
        "messages": [AIMessage(content=_format_cancel_preview(preview_payload))],
    }

def request_clarification(state: State):
    return {}

# --- Agent Nodes ---
def orchestrator(state: AgentState, llm_with_tools):
    context_summary = state.get("context_summary", "").strip()
    sys_msg = SystemMessage(content=get_orchestrator_prompt())
    summary_injection = (
        [HumanMessage(content=f"[COMPRESSED CONTEXT FROM PRIOR RESEARCH]\n\n{context_summary}")]
        if context_summary else []
    )
    if not state.get("messages"):
        human_msg = HumanMessage(content=state["question"])
        force_search = HumanMessage(content="YOU MUST CALL 'search_child_chunks' AS THE FIRST STEP TO ANSWER THIS QUESTION.")
        response = llm_with_tools.invoke([sys_msg] + summary_injection + [human_msg, force_search])
        return {"messages": [human_msg, response], "tool_call_count": len(response.tool_calls or []), "iteration_count": 1}

    response = llm_with_tools.invoke([sys_msg] + summary_injection + state["messages"])
    tool_calls = response.tool_calls if hasattr(response, "tool_calls") else []
    return {"messages": [response], "tool_call_count": len(tool_calls) if tool_calls else 0, "iteration_count": 1}

def fallback_response(state: AgentState, llm):
    seen = set()
    unique_contents = []
    for m in state["messages"]:
        if isinstance(m, ToolMessage) and m.content not in seen:
            unique_contents.append(m.content)
            seen.add(m.content)

    context_summary = state.get("context_summary", "").strip()

    context_parts = []
    if context_summary:
        context_parts.append(f"## Compressed Research Context (from prior iterations)\n\n{context_summary}")
    if unique_contents:
        context_parts.append(
            "## Retrieved Data (current iteration)\n\n" +
            "\n\n".join(f"--- DATA SOURCE {i} ---\n{content}" for i, content in enumerate(unique_contents, 1))
        )

    context_text = "\n\n".join(context_parts) if context_parts else "No data was retrieved from the documents."

    prompt_content = (
        f"USER QUERY: {state.get('question')}\n\n"
        f"{context_text}\n\n"
        f"INSTRUCTION:\nProvide the best possible answer using only the data above."
    )
    response = llm.invoke([SystemMessage(content=get_fallback_response_prompt()), HumanMessage(content=prompt_content)])
    return {"messages": [response]}

def should_compress_context(state: AgentState) -> Command[Literal["compress_context", "orchestrator"]]:
    messages = state["messages"]

    new_ids: Set[str] = set()
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                if tc["name"] == "retrieve_parent_chunks":
                    raw = tc["args"].get("parent_id") or tc["args"].get("id") or tc["args"].get("ids") or []
                    if isinstance(raw, str):
                        new_ids.add(f"parent::{raw}")
                    else:
                        new_ids.update(f"parent::{r}" for r in raw)

                elif tc["name"] == "search_child_chunks":
                    query = tc["args"].get("query", "")
                    if query:
                        new_ids.add(f"search::{query}")
            break

    updated_ids = state.get("retrieval_keys", set()) | new_ids

    current_token_messages = estimate_context_tokens(messages)
    current_token_summary = estimate_context_tokens([HumanMessage(content=state.get("context_summary", ""))])
    current_tokens = current_token_messages + current_token_summary

    max_allowed = BASE_TOKEN_THRESHOLD + int(current_token_summary * TOKEN_GROWTH_FACTOR)

    goto = "compress_context" if current_tokens > max_allowed else "orchestrator"
    return Command(update={"retrieval_keys": updated_ids}, goto=goto)

def compress_context(state: AgentState, llm):
    messages = state["messages"]
    existing_summary = state.get("context_summary", "").strip()

    if not messages:
        return {}

    conversation_text = f"USER QUESTION:\n{state.get('question')}\n\nConversation to compress:\n\n"
    if existing_summary:
        conversation_text += f"[PRIOR COMPRESSED CONTEXT]\n{existing_summary}\n\n"

    for msg in messages[1:]:
        if isinstance(msg, AIMessage):
            tool_calls_info = ""
            if getattr(msg, "tool_calls", None):
                calls = ", ".join(f"{tc['name']}({tc['args']})" for tc in msg.tool_calls)
                tool_calls_info = f" | Tool calls: {calls}"
            conversation_text += f"[ASSISTANT{tool_calls_info}]\n{msg.content or '(tool call only)'}\n\n"
        elif isinstance(msg, ToolMessage):
            tool_name = getattr(msg, "name", "tool")
            conversation_text += f"[TOOL RESULT — {tool_name}]\n{msg.content}\n\n"

    summary_response = llm.invoke([SystemMessage(content=get_context_compression_prompt()), HumanMessage(content=conversation_text)])
    new_summary = summary_response.content

    retrieved_ids: Set[str] = state.get("retrieval_keys", set())
    if retrieved_ids:
        parent_ids = sorted(r for r in retrieved_ids if r.startswith("parent::"))
        search_queries = sorted(r.replace("search::", "") for r in retrieved_ids if r.startswith("search::"))

        block = "\n\n---\n**Already executed (do NOT repeat):**\n"
        if parent_ids:
            block += "Parent chunks retrieved:\n" + "\n".join(f"- {p.replace('parent::', '')}" for p in parent_ids) + "\n"
        if search_queries:
            block += "Search queries already run:\n" + "\n".join(f"- {q}" for q in search_queries) + "\n"
        new_summary += block

    return {"context_summary": new_summary, "messages": [RemoveMessage(id=m.id) for m in messages[1:]]}

def collect_answer(state: AgentState):
    last_message = state["messages"][-1]
    is_valid = isinstance(last_message, AIMessage) and last_message.content and not last_message.tool_calls
    answer = last_message.content if is_valid else "Unable to generate an answer."
    return {
        "final_answer": answer,
        "agent_answers": [{"index": state["question_index"], "question": state["question"], "answer": answer}]
    }
# --- End of Agent Nodes---

def aggregate_answers(state: State, llm):
    if not state.get("agent_answers"):
        return {"messages": [AIMessage(content="No answers were generated.")]}

    sorted_answers = sorted(state["agent_answers"], key=lambda x: x["index"])

    formatted_answers = ""
    for i, ans in enumerate(sorted_answers, start=1):
        formatted_answers += (f"\nAnswer {i}:\n"f"{ans['answer']}\n")

    user_message = HumanMessage(content=f"""Original user question: {state["originalQuery"]}\nRetrieved answers:{formatted_answers}""")
    synthesis_response = llm.invoke([SystemMessage(content=get_aggregation_prompt()), user_message])
    return {"messages": [AIMessage(content=synthesis_response.content)]}
