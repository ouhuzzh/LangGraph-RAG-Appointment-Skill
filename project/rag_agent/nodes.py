import re
import uuid
from typing import Literal, Set
from datetime import date, timedelta
from langchain_core.messages import SystemMessage, HumanMessage, RemoveMessage, AIMessage, ToolMessage
from langchain_core.documents import Document
from langgraph.types import Command
from .graph_state import State, AgentState
from .schemas import (
    QueryAnalysis,
    IntentAnalysis,
    DepartmentRecommendation,
    AppointmentActionCall,
    CancelActionCall,
    AppointmentSkillRequest,
    RetrievalQueryPlan,
    GroundedAnswerCheck,
)
from .prompts import *
from utils import estimate_context_tokens
import config
from config import BASE_TOKEN_THRESHOLD, TOKEN_GROWTH_FACTOR, HIGH_RISK_KEYWORDS
from db.appointment_skill_log_store import AppointmentSkillLogStore
from services.appointment_skill import AppointmentSkill
from rag_agent.tools import plan_queries, ground_answer

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
_MEDICAL_TERMS = (
    "高血压", "糖尿病", "感冒", "发烧", "头晕", "咳嗽", "腹痛", "胃痛", "胸闷", "胸痛",
    "呼吸困难", "肺炎", "哮喘", "鼻炎", "胃炎", "肠胃炎", "失眠", "焦虑", "抑郁",
    "血压", "血糖", "检查", "药", "症状", "疾病", "炎", "癌", "病", "疫苗", "预防", "指南", "综合征",
    "hypertension", "diabetes", "fever", "cough", "dizziness", "headache", "pneumonia",
    "asthma", "symptom", "treatment", "disease", "medicine", "blood pressure",
)
_MEDICAL_QUESTION_PATTERNS = (
    "是什么", "怎么回事", "为什么", "原因", "症状", "表现", "怎么办", "如何", "怎么处理",
    "怎么缓解", "严重吗", "会不会", "会引起", "会导致", "能不能", "可以吗", "要不要",
    "是否", "注意事项", "治疗", "预防", "要紧吗", "还要看吗", "哪些人", "什么人", "什么时候", "是不是",
    "几片", "几粒", "几次", "剂量", "怎么吃", "怎么服用", "一天吃", "一天用", "多久吃一次", "多久用一次",
    "means", "what is", "why", "how to", "symptoms",
    "treatment", "can ", "could ", "does ", "is it",
)
_APPOINTMENT_KEYWORDS = ("挂号", "预约", "book appointment", "register")
_CANCEL_KEYWORDS = ("取消", "退号", "cancel appointment", "cancel booking")
_EXPLICIT_APPOINTMENT_CUES = ("帮我", "给我", "我要", "想", "安排", "预约一下", "挂一下", "register me", "book me")
_EXPLICIT_CANCEL_CUES = ("取消预约", "取消挂号", "退号", "帮我取消", "取消刚才", "cancel", "取消那个")
_COMPOUND_SPLIT_RE = re.compile(r"(?:，|,)?\s*(另外|然后|然后再|顺便|并且|同时|再帮我|再问一下)\s*")
_DEPARTMENT_HINTS = (
    "呼吸内科", "心内科", "神经内科", "消化内科", "内分泌科", "急诊科", "全科", "儿科",
    "妇科", "骨科", "皮肤科", "耳鼻喉科", "眼科", "呼吸科", "内科", "外科", "门诊",
)
_TOPIC_STOP_WORDS = ("一下", "一下子", "这个", "那个", "这种情况", "怎么", "怎么办", "需要", "是否", "一般")
_ANY_DOCTOR_HINTS = ("任一", "任何医生", "随便医生", "都可以", "任选", "任意医生", "任一可用医生")
_EARLIEST_SLOT_HINTS = ("最早可用时段", "最早的", "最早号源", "最快的", "尽快")
_DOCTOR_DISCOVERY_HINTS = ("有哪些医生", "哪个医生", "医生有号", "谁有号", "查医生", "医生排班", "专家", "号源")
_APPOINTMENT_LIST_HINTS = (
    "我的预约", "有哪些预约", "查预约", "看看预约", "预约列表",
    "挂了谁的号", "挂的是谁的号", "我挂了谁的号", "我之前挂了谁的号",
    "我现在挂了谁的号", "预约了谁", "约了谁的号",
)
_RESCHEDULE_HINTS = ("改约", "改到", "换到", "换成", "改成", "挪到")
_GENERAL_CHAT_HINTS = (
    "我今天有点烦", "有点烦", "心情不好", "不开心", "有点累", "有点焦虑", "想聊聊", "聊聊",
    "谢谢你", "谢谢", "晚安", "早安", "中午好", "晚上好",
)
_NON_MEDICAL_TOPIC_HINTS = (
    "东京", "旅游", "景点", "好玩", "美食", "电影", "书", "天气", "旅行", "推荐一下", "介绍一下",
    "有什么好玩的", "周末去哪", "想放松", "可以聊聊天吗",
)
_MEDICATION_RISK_HINTS = (
    "一天吃几片", "一次吃几片", "一天几次", "一次几次", "剂量", "毫克", "mg", "用量", "服用",
    "怎么吃", "多久吃一次", "多久用一次", "bid", "tid", "qd",
)
_APPOINTMENT_SKILL_LOG_STORE = None


def _clear_pending_action_state() -> dict:
    return {
        "pending_action_type": "",
        "pending_action_payload": {},
        "pending_confirmation_id": "",
        "pending_candidates": [],
    }


def _get_appointment_skill_log_store():
    global _APPOINTMENT_SKILL_LOG_STORE
    if _APPOINTMENT_SKILL_LOG_STORE is None:
        _APPOINTMENT_SKILL_LOG_STORE = AppointmentSkillLogStore()
    return _APPOINTMENT_SKILL_LOG_STORE


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

    has_medical_term = any(term in normalized for term in _MEDICAL_TERMS)
    has_disease_suffix = bool(re.search(r"(综合征|感染|病|炎|癌|瘤)", normalized))
    has_question_pattern = any(pattern in normalized for pattern in _MEDICAL_QUESTION_PATTERNS) or normalized.endswith("?") or normalized.endswith("？") or normalized.endswith("吗")
    return (has_medical_term or has_disease_suffix) and has_question_pattern


def _looks_like_medication_risk_query(query: str) -> bool:
    normalized = (query or "").strip().lower()
    return any(token in normalized for token in _MEDICATION_RISK_HINTS)


def _looks_like_medical_request(query: str, *, conversation_summary: str = "", recent_context: str = "", topic_focus: str = "") -> bool:
    normalized = (query or "").strip().lower()
    if not normalized:
        return False
    if _looks_like_department_question(query):
        return True
    if _looks_like_medical_knowledge_question(query) or _looks_like_medication_risk_query(query):
        return True
    if any(keyword.lower() in normalized for keyword in HIGH_RISK_KEYWORDS):
        return True
    if any(term in normalized for term in _MEDICAL_TERMS):
        return True
    context_text = "\n".join(part for part in (conversation_summary, recent_context, topic_focus) if str(part or "").strip())
    if any(token in normalized for token in _MEDICAL_FOLLOW_UP_HINTS) and _context_has_medical_signal(context_text):
        return True
    return False


def _looks_like_general_non_medical_query(query: str) -> bool:
    normalized = (query or "").strip().lower()
    if not normalized:
        return False
    if _looks_like_greeting(query):
        return True
    if _looks_like_medical_request(query) or _looks_like_explicit_appointment_intent(query) or _looks_like_explicit_cancel_intent(query):
        return False
    if any(token in normalized for token in _GENERAL_CHAT_HINTS):
        return True
    if any(token in normalized for token in _NON_MEDICAL_TOPIC_HINTS):
        return True
    if len(normalized) <= 20 and any(token in normalized for token in ("烦", "累", "无聊", "难过", "开心", "聊", "心情")):
        return True
    return False


def _needs_strict_medical_safety(query: str, risk_level: str = "normal") -> bool:
    return risk_level == "high" or _looks_like_medication_risk_query(query)


def _needs_medication_detail_clarification(query: str) -> bool:
    normalized = (query or "").strip().lower()
    vague_reference = any(token in normalized for token in ("这个药", "这药", "这种药", "它"))
    return vague_reference and _looks_like_medication_risk_query(query)


def _build_medical_fallback_notice(*, risk_level: str = "normal", confidence_bucket: str = "no_evidence") -> str:
    mode_label = "回答模式：通用医学信息回答（本次未充分基于知识库检索结果）" if confidence_bucket == "no_evidence" else "回答模式：通用医学信息回答（知识库证据有限）"
    notice = (
        f"{mode_label}\n\n"
        "提醒：以上内容仅供一般医学信息参考，当前回答未充分基于知识库检索结果，不能替代专业医生面对面诊断。"
    )
    if risk_level == "high":
        notice += "\n如症状严重、持续加重，或出现胸痛、呼吸困难、意识异常等情况，请尽快线下就医或急诊评估。"
    else:
        notice += "\n如症状持续加重，或涉及用药、剂量、急症判断，请及时就医。"
    return notice


def _normalize_time_slot(raw_value: str) -> str:
    normalized = (raw_value or "").strip().lower()
    if not normalized:
        return ""
    if normalized in {"morning", "afternoon", "evening"}:
        return normalized
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
        if value or (key in updates and isinstance(value, list)):
            context[key] = _json_safe_value(value)
    return context


def _json_safe_value(value):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]
    return value


def _sanitize_pending_payload(payload: dict | None) -> dict:
    cleaned = dict(payload or {})
    for key in ("department", "date", "time_slot", "doctor_name", "appointment_no", "action"):
        value = cleaned.get(key)
        if isinstance(value, str):
            cleaned[key] = value.strip()
    return cleaned


def _extract_topic_focus(user_query: str, existing_topic: str = "", appointment_context: dict | None = None, recommended_department: str = "") -> str:
    normalized = (user_query or "").strip()
    for term in _MEDICAL_TERMS:
        if term in normalized.lower():
            return term
    for department in _DEPARTMENT_HINTS:
        if department in normalized:
            return department
    if recommended_department:
        return recommended_department
    appointment_context = appointment_context or {}
    for key in ("department", "doctor_name"):
        value = (appointment_context.get(key) or "").strip()
        if value:
            return value
    existing_topic = (existing_topic or "").strip()
    return existing_topic


def _wants_any_available_doctor(user_query: str) -> bool:
    normalized = (user_query or "").strip().lower()
    return any(token in normalized for token in _ANY_DOCTOR_HINTS)


def _pick_doctor_name_from_text(user_query: str, doctor_options: list[dict] | None) -> str:
    normalized = (user_query or "").strip().lower()
    for item in doctor_options or []:
        doctor_name = str(item.get("doctor_name") or "").strip()
        if doctor_name and doctor_name.lower() in normalized:
            return doctor_name
    return ""


def _wants_earliest_available_slot(user_query: str) -> bool:
    normalized = (user_query or "").strip().lower()
    return any(token in normalized for token in _EARLIEST_SLOT_HINTS)


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
    }


def _format_doctor_slot_selection_message(department: str, doctor_name: str, options: list[dict]) -> str:
    lines = [
        f"{idx}. **{item.get('schedule_date')} {item.get('time_slot')}**（剩余号源 {item.get('quota_available', 0)}）"
        for idx, item in enumerate(_sort_schedule_options(options)[:8], start=1)
    ]
    return (
        f"我找到 **{department}** 的 **{doctor_name}** 可预约时段：\n\n"
        + "\n".join(lines)
        + "\n\n你可以直接回复具体日期和时段，例如“2026-04-18 下午”；如果你希望我直接优先选最早可用时段，也可以回复 **最早可用时段**。"
    )


def _strip_leading_query_plan_blob(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return raw
    patterns = [
        r'^\s*```(?:json)?\s*\{\s*"queries"\s*:\s*\[[\s\S]*?\]\s*\}\s*```\s*',
        r'^\s*\{\s*"queries"\s*:\s*\[[\s\S]*?\]\s*\}\s*',
    ]
    cleaned = raw
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, count=1, flags=re.IGNORECASE)
        if cleaned != raw:
            break
    return cleaned.strip() or raw


def _strip_trailing_sources_block(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return cleaned
    patterns = [
        r'\n\s*---\s*\n\s*\*\*Sources:\*\*\s*\n(?:\s*[-*].*(?:\n|$))+?\s*$',
        r'\n\s*\*\*Sources:\*\*\s*\n(?:\s*[-*].*(?:\n|$))+?\s*$',
        r'\n\s*参考来源：\s*\n(?:\s*[-*].*(?:\n|$))+?\s*$',
    ]
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _sanitize_final_answer_text(text: str) -> str:
    cleaned = _strip_leading_query_plan_blob(text)
    cleaned = _strip_trailing_sources_block(cleaned)
    return cleaned.strip()


def _confidence_bucket_label(confidence_bucket: str) -> str:
    mapping = {
        "high": "高",
        "medium": "中",
        "low": "低",
        "no_evidence": "未命中足够证据",
    }
    return mapping.get(str(confidence_bucket or "").strip().lower(), "未知")


def _confidence_bucket_explanation(confidence_bucket: str, *, is_medical_request: bool = False) -> str:
    normalized = str(confidence_bucket or "").strip().lower()
    if normalized == "high":
        return "当前回答主要依据知识库中较直接、较匹配的资料整理而成。"
    if normalized == "medium":
        return "当前回答参考了相关资料，但证据覆盖还不算充分，适合先作为初步参考。"
    if normalized == "low":
        return (
            "当前回答仅参考到少量相关资料，结论应保持保守。"
            if is_medical_request
            else "当前回答只参考到有限资料，可作为一般性参考。"
        )
    if normalized == "no_evidence":
        return (
            "知识库这次没有命中足够直接的相关资料，因此以下内容更偏通用医学信息。"
            if is_medical_request
            else "知识库这次没有命中足够直接的相关资料。"
        )
    return ""


def _source_type_label(source_type: str) -> str:
    mapping = {
        "patient_education": "患者教育",
        "public_health": "公共卫生",
        "clinical_guideline": "临床指南",
        "research_article": "研究资料",
        "unknown": "资料",
    }
    normalized = str(source_type or "").strip().lower()
    return mapping.get(normalized, normalized or "资料")


def _freshness_bucket_label(bucket: str) -> str:
    mapping = {
        "fresh": "较新",
        "current": "当前",
        "outdated": "较旧",
        "stale": "较旧",
    }
    normalized = str(bucket or "").strip().lower()
    return mapping.get(normalized, "")


def _format_reference_lines(sources: list[dict]) -> list[str]:
    lines = []
    for item in sources[:3]:
        title = str(item.get("title") or "未知来源").strip()
        source_label = _source_type_label(item.get("source_type", ""))
        freshness_label = _freshness_bucket_label(item.get("freshness_bucket", ""))
        meta_parts = [source_label]
        if freshness_label:
            meta_parts.append(f"时效：{freshness_label}")
        line = f"- {title}"
        if meta_parts:
            line += f"（{'，'.join(meta_parts)}）"
        original_url = str(item.get("original_url") or "").strip()
        if original_url:
            line += f" [链接]({original_url})"
        lines.append(line)
    return lines


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


def _is_explicit_confirmation(user_query: str, pending_action_type: str) -> bool:
    normalized = (user_query or "").strip().lower()
    if not normalized:
        return False
    if pending_action_type in {"appointment", "reschedule_appointment"}:
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
    hints = ("最近的", "上次", "刚刚", "刚才", "上一个", "上一条", "那个预约", "这条预约")
    return any(token in normalized for token in hints)


def _build_recent_context(messages, keep_turns: int | None = None, *, exclude_latest_user: bool = True) -> str:
    if keep_turns is None:
        keep_turns = max(int(getattr(config, "RECENT_CONTEXT_TURNS", 3) or 3), 1)
    recent_messages = [
        msg for msg in (messages or [])
        if isinstance(msg, (HumanMessage, AIMessage)) and not getattr(msg, "tool_calls", None)
    ]
    if exclude_latest_user and recent_messages and isinstance(recent_messages[-1], HumanMessage):
        recent_messages = recent_messages[:-1]
    recent_messages = recent_messages[-keep_turns * 2 :]
    lines = []
    for msg in recent_messages:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        content = str(msg.content or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _context_has_medical_signal(text: str) -> bool:
    normalized = (text or "").strip().lower()
    return any(term in normalized for term in _MEDICAL_TERMS)


def _looks_like_medical_follow_up(user_query: str, conversation_summary: str, recent_context: str = "") -> bool:
    normalized = (user_query or "").strip().lower()
    context_text = "\n".join(part for part in (conversation_summary, recent_context) if part and str(part).strip())
    if not normalized or not context_text.strip():
        return False
    if not any(token in normalized for token in _MEDICAL_FOLLOW_UP_HINTS):
        return False
    return _context_has_medical_signal(context_text)


def _looks_like_explicit_appointment_intent(user_query: str) -> bool:
    normalized = (user_query or "").strip().lower()
    has_booking_keyword = any(keyword in normalized for keyword in _APPOINTMENT_KEYWORDS) or (
        "挂" in normalized and not _looks_like_department_question(user_query)
    )
    if not normalized or not has_booking_keyword:
        return False
    if re.search(r"(预约|挂号|挂)前", normalized):
        return False

    explicit_cue = any(token in normalized for token in _EXPLICIT_APPOINTMENT_CUES)
    scheduling_cue = bool(_normalize_date(user_query) or _normalize_time_slot(user_query))
    entity_cue = any(token in normalized for token in ("医生", "门诊", "内科", "外科", "呼吸科", "呼吸内科", "儿科", "妇科", "科室"))

    if _looks_like_medical_knowledge_question(user_query) and not (explicit_cue or scheduling_cue or entity_cue):
        return False
    return explicit_cue or scheduling_cue or entity_cue


def _looks_like_appointment_discovery_query(user_query: str) -> bool:
    normalized = (user_query or "").strip().lower()
    if not normalized:
        return False
    if _looks_like_department_question(user_query):
        return False
    if any(token in normalized for token in _APPOINTMENT_LIST_HINTS):
        return True
    if any(token in normalized for token in _DOCTOR_DISCOVERY_HINTS):
        return True
    if "有哪些科室" in normalized or "什么科室" in normalized:
        return True
    if "有号吗" in normalized and ("医生" in normalized or any(dep in normalized for dep in _DEPARTMENT_HINTS)):
        return True
    return False


def _looks_like_department_name_only(user_query: str) -> bool:
    normalized = (user_query or "").strip()
    if not normalized:
        return False
    return any(department in normalized for department in _DEPARTMENT_HINTS)


def _looks_like_explicit_cancel_intent(user_query: str) -> bool:
    normalized = (user_query or "").strip().lower()
    if not normalized or not any(keyword in normalized for keyword in _CANCEL_KEYWORDS):
        return False
    if _looks_like_medical_knowledge_question(user_query) and not (_should_use_last_appointment(user_query) or _APPOINTMENT_NO_RE.search(user_query or "")):
        return False
    return (
        any(token in normalized for token in _EXPLICIT_CANCEL_CUES)
        or _should_use_last_appointment(user_query)
        or bool(_APPOINTMENT_NO_RE.search(user_query or ""))
    )


def _looks_like_clarification_response(user_query: str) -> bool:
    normalized = (user_query or "").strip().lower()
    if not normalized:
        return False
    if _looks_like_greeting(user_query) or _looks_like_department_question(user_query):
        return False
    if _looks_like_explicit_cancel_intent(user_query) or _looks_like_explicit_appointment_intent(user_query):
        return False
    if _looks_like_medical_knowledge_question(user_query):
        return False
    if len(normalized) <= 40:
        return True
    return bool(
        _normalize_date(user_query)
        or _normalize_time_slot(user_query)
        or _APPOINTMENT_NO_RE.search(user_query or "")
        or _ORDINAL_RE.search(user_query or "")
    )


def _intent_for_clarification_target(target: str, current_intent: str) -> str:
    if target == "recommend_department":
        return "triage"
    if target == "handle_appointment_skill":
        return current_intent or "appointment"
    if target == "handle_appointment":
        return "appointment"
    if target == "handle_cancel_appointment":
        return "cancel_appointment"
    if target == "rewrite_query":
        return "medical_rag"
    return current_intent or "medical_rag"


def _classify_query_by_rules(user_query: str, *, conversation_summary: str = "", recent_context: str = "", topic_focus: str = "") -> tuple[str, str]:
    if _looks_like_greeting(user_query):
        return "greeting", "greeting_rule"
    if _looks_like_explicit_cancel_intent(user_query):
        return "cancel_appointment", "explicit_cancel_rule"
    if _looks_like_appointment_discovery_query(user_query):
        return "appointment", "appointment_discovery_rule"
    if _looks_like_explicit_appointment_intent(user_query):
        return "appointment", "explicit_appointment_rule"
    if _looks_like_department_question(user_query):
        return "triage", "department_question_rule"
    if _looks_like_medical_knowledge_question(user_query) or _looks_like_medical_follow_up(
        user_query,
        "\n".join(part for part in (conversation_summary, topic_focus) if part),
        recent_context,
    ):
        return "medical_rag", "medical_question_rule"
    if _looks_like_general_non_medical_query(user_query):
        return "medical_rag", "general_conversation_rule"
    return "", "rule_inconclusive"


def _split_compound_request(user_query: str) -> list[str]:
    query = (user_query or "").strip()
    if not query:
        return []
    segments = [segment.strip(" ，,。；;") for segment in _COMPOUND_SPLIT_RE.split(query) if segment and segment.strip(" ，,。；;")]
    cleaned = []
    for segment in segments:
        if segment in {"另外", "然后", "然后再", "顺便", "并且", "同时", "再帮我", "再问一下"}:
            continue
        cleaned.append(segment)
    if not cleaned:
        return [query]
    if len(cleaned) == 1:
        return cleaned
    return cleaned[:2]


def _choose_compound_intents(first_intent: str, second_intent: str) -> tuple[str, str]:
    if (first_intent, second_intent) in {
        ("cancel_appointment", "medical_rag"),
        ("appointment", "medical_rag"),
        ("triage", "appointment"),
        ("triage", "medical_rag"),
    }:
        return first_intent, second_intent
    if (first_intent, second_intent) == ("medical_rag", "appointment"):
        return "appointment", "medical_rag"
    return first_intent, ""


def analyze_turn(state: State):
    last_message = state["messages"][-1]
    user_query = str(last_message.content).strip()
    recent_context = state.get("recent_context") or _build_recent_context(state.get("messages", []))
    topic_focus = _extract_topic_focus(
        user_query,
        state.get("topic_focus", ""),
        state.get("appointment_context", {}),
        state.get("recommended_department", ""),
    )

    if state.get("pending_action_type") and _should_continue_pending_action(state, user_query):
        primary_intent = state.get("pending_action_type", "")
        return {
            "recent_context": recent_context,
            "topic_focus": topic_focus or state.get("topic_focus", ""),
            "primary_intent": primary_intent,
            "secondary_intent": state.get("secondary_intent", ""),
            "primary_user_query": user_query,
            "secondary_user_query": state.get("secondary_user_query", ""),
            "deferred_user_question": state.get("deferred_user_question", ""),
            "decision_source": "resume",
            "route_reason": "continue_pending_action",
            "last_route_reason": "continue_pending_action",
        }

    if state.get("pending_candidates") and _pick_candidate_from_text(user_query, state.get("pending_candidates") or []):
        return {
            "recent_context": recent_context,
            "topic_focus": topic_focus or state.get("topic_focus", ""),
            "primary_intent": "cancel_appointment",
            "secondary_intent": state.get("secondary_intent", ""),
            "primary_user_query": user_query,
            "secondary_user_query": state.get("secondary_user_query", ""),
            "deferred_user_question": state.get("deferred_user_question", ""),
            "decision_source": "resume",
            "route_reason": "continue_pending_candidates",
            "last_route_reason": "continue_pending_candidates",
        }

    clarification_target = state.get("clarification_target", "")
    if state.get("pending_clarification") and clarification_target and _looks_like_clarification_response(user_query):
        primary_intent = _intent_for_clarification_target(clarification_target, state.get("intent", ""))
        return {
            "recent_context": recent_context,
            "topic_focus": topic_focus or state.get("topic_focus", ""),
            "primary_intent": primary_intent,
            "secondary_intent": state.get("secondary_intent", ""),
            "primary_user_query": user_query,
            "secondary_user_query": state.get("secondary_user_query", ""),
            "deferred_user_question": state.get("deferred_user_question", ""),
            "decision_source": "resume",
            "route_reason": f"continue_{clarification_target}",
            "last_route_reason": f"continue_{clarification_target}",
        }

    if (
        (state.get("intent") == "appointment" or state.get("appointment_skill_mode") in {"discover_department", "clarify", "discover_doctor", "discover_availability"})
        and _looks_like_department_name_only(user_query)
        and not _looks_like_explicit_cancel_intent(user_query)
    ):
        return {
            "recent_context": recent_context,
            "topic_focus": _extract_topic_focus(
                user_query,
                state.get("topic_focus", ""),
                state.get("appointment_context", {}),
                state.get("recommended_department", ""),
            ),
            "primary_intent": "appointment",
            "secondary_intent": "",
            "primary_user_query": user_query,
            "secondary_user_query": "",
            "deferred_user_question": "",
            "decision_source": "resume",
            "route_reason": "continue_department_selection",
            "last_route_reason": "continue_department_selection",
        }

    segments = _split_compound_request(user_query)
    first_segment = segments[0] if segments else user_query
    second_segment = segments[1] if len(segments) > 1 else ""
    first_intent, first_reason = _classify_query_by_rules(
        first_segment,
        conversation_summary=state.get("conversation_summary", ""),
        recent_context=recent_context,
        topic_focus=state.get("topic_focus", ""),
    )
    second_intent = ""
    second_reason = ""
    if second_segment:
        second_intent, second_reason = _classify_query_by_rules(
            second_segment,
            conversation_summary=state.get("conversation_summary", ""),
            recent_context=recent_context,
            topic_focus=state.get("topic_focus", ""),
        )
    primary_intent, secondary_intent = _choose_compound_intents(first_intent, second_intent)
    if primary_intent:
        route_reason = first_reason if not secondary_intent else f"{first_reason}+{second_reason or 'secondary'}"
        return {
            "recent_context": recent_context,
            "topic_focus": topic_focus or state.get("topic_focus", ""),
            "primary_intent": primary_intent,
            "secondary_intent": secondary_intent,
            "primary_user_query": first_segment if secondary_intent else user_query,
            "secondary_user_query": second_segment if secondary_intent else "",
            "deferred_user_question": second_segment if secondary_intent else "",
            "decision_source": "rule",
            "route_reason": route_reason,
            "last_route_reason": route_reason,
        }

    return {
        "recent_context": recent_context,
        "topic_focus": topic_focus or state.get("topic_focus", ""),
        "primary_intent": "",
        "secondary_intent": "",
        "primary_user_query": user_query,
        "secondary_user_query": "",
        "deferred_user_question": "",
        "decision_source": "llm",
        "route_reason": "rule_inconclusive",
        "last_route_reason": "rule_inconclusive",
    }


def _build_history_reset_messages(messages, keep_recent: int = 5):
    non_system_messages = [m for m in messages if not isinstance(m, SystemMessage)]
    keep_ids = {getattr(m, "id", None) for m in non_system_messages[-keep_recent:]}
    delete_messages = []
    for message in non_system_messages:
        message_id = getattr(message, "id", None)
        if message_id and message_id not in keep_ids:
            delete_messages.append(RemoveMessage(id=message_id))
    return delete_messages


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


def _format_reschedule_confirmation_preview(payload: dict) -> str:
    previous_doctor = payload.get("previous_doctor_name") or "未指定"
    next_doctor = payload.get("doctor_name") or "未指定"
    return (
        "我已整理好改约信息，请回复 **确认预约** 来正式提交改约：\n\n"
        f"- 原预约：**{payload['previous_department']}**，**{payload['previous_date']}**，**{payload['previous_time_slot']}**，医生：**{previous_doctor}**\n"
        f"- 新预约：**{payload['department']}**，**{payload['date']}**，**{payload['time_slot']}**，医生：**{next_doctor}**\n\n"
        "如果你想再换一个日期、时段或医生，直接告诉我新的要求即可。"
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
    if not state.get("primary_intent"):
        state = {**state, **analyze_turn(state)}
    last_message = state["messages"][-1]
    user_query = str(last_message.content).strip()
    risk_level = _infer_risk_level(user_query, state.get("risk_level", "normal"))
    pending_action_type = state.get("pending_action_type", "")
    pending_candidates = state.get("pending_candidates", []) or []
    recent_context = state.get("recent_context") or _build_recent_context(state.get("messages", []))
    topic_focus = state.get("topic_focus", "")
    primary_intent = state.get("primary_intent", "")
    secondary_intent = state.get("secondary_intent", "")
    primary_user_query = state.get("primary_user_query", "") or user_query
    secondary_user_query = state.get("secondary_user_query", "")
    decision_source = state.get("decision_source", "")
    route_reason = state.get("route_reason", "")

    if _needs_medication_detail_clarification(primary_user_query):
        clarification = "请先告诉我药名、规格或包装上写的剂量信息，我才能更安全地帮你判断怎么用。"
        return {
            "intent": "clarification",
            "primary_intent": "clarification",
            "secondary_intent": "",
            "primary_user_query": primary_user_query,
            "secondary_user_query": "",
            "decision_source": "rule",
            "route_reason": "medication_dose_needs_details",
            "last_route_reason": "medication_dose_needs_details",
            "risk_level": "high",
            "pending_clarification": clarification,
            "clarification_target": "intent_router",
            "recent_context": recent_context,
            "topic_focus": topic_focus or _extract_topic_focus(primary_user_query, topic_focus),
            "deferred_user_question": "",
            "clarification_attempts": 1,
            "recommended_department": state.get("recommended_department", ""),
            "appointment_context": state.get("appointment_context", {}),
            "last_appointment_no": state.get("last_appointment_no", ""),
            **_reset_pending_action_if_needed(state),
            "messages": [AIMessage(content=clarification)],
        }

    if primary_intent == "greeting":
        greeting_response = "你好！我是你的医疗助手，可以帮你：\n- 🏥 推荐就诊科室\n- 📅 预约挂号\n- ❌ 取消预约\n- 💊 解答医疗健康问题\n\n请问有什么可以帮你的？"
        return {
            "intent": "greeting",
            "primary_intent": "greeting",
            "secondary_intent": "",
            "primary_user_query": primary_user_query,
            "secondary_user_query": "",
            "decision_source": decision_source or "rule",
            "route_reason": route_reason or "greeting_rule",
            "last_route_reason": route_reason or "greeting_rule",
            "risk_level": risk_level,
            "pending_clarification": "",
            "clarification_target": "",
            "recent_context": recent_context,
            "topic_focus": topic_focus,
            "deferred_user_question": "",
            "clarification_attempts": 0,
            "recommended_department": state.get("recommended_department", ""),
            "appointment_context": state.get("appointment_context", {}),
            "last_appointment_no": state.get("last_appointment_no", ""),
            **_reset_pending_action_if_needed(state),
            "messages": [AIMessage(content=greeting_response)],
        }

    if primary_intent in {"triage", "appointment", "cancel_appointment", "medical_rag"}:
        if primary_intent == "triage":
            pending_updates = _clear_pending_action_state()
            recommended_department = ""
            appointment_context = {}
            last_appointment_no = ""
        elif primary_intent == "medical_rag":
            pending_updates = _reset_pending_action_if_needed(state)
            recommended_department = state.get("recommended_department", "")
            appointment_context = state.get("appointment_context", {})
            last_appointment_no = state.get("last_appointment_no", "")
        else:
            pending_updates = {
                "pending_action_type": pending_action_type,
                "pending_action_payload": state.get("pending_action_payload", {}),
                "pending_confirmation_id": state.get("pending_confirmation_id", ""),
                "pending_candidates": pending_candidates,
            }
            recommended_department = state.get("recommended_department", "")
            appointment_context = state.get("appointment_context", {})
            last_appointment_no = state.get("last_appointment_no", "")
        return {
            "intent": primary_intent,
            "primary_intent": primary_intent,
            "secondary_intent": secondary_intent,
            "primary_user_query": primary_user_query,
            "secondary_user_query": secondary_user_query,
            "decision_source": decision_source or "rule",
            "route_reason": route_reason or "rule_match",
            "last_route_reason": route_reason or "rule_match",
            "risk_level": risk_level,
            "pending_clarification": "",
            "clarification_target": "",
            "recent_context": recent_context,
            "topic_focus": topic_focus,
            "deferred_user_question": state.get("deferred_user_question", "") or secondary_user_query,
            "clarification_attempts": 0,
            "recommended_department": recommended_department,
            "appointment_context": appointment_context,
            "last_appointment_no": last_appointment_no,
            **pending_updates,
        }

    llm_with_structure = llm.with_config(temperature=0.1).with_structured_output(IntentAnalysis)
    response = llm_with_structure.invoke(
        [
            SystemMessage(content=get_intent_router_prompt()),
            HumanMessage(
                content=(
                    f"Conversation summary:\n{state.get('conversation_summary', '')}\n\n"
                    f"Recent dialogue context:\n{recent_context}\n\n"
                    f"User query:\n{user_query}"
                )
            ),
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
            "primary_intent": response.intent,
            "secondary_intent": "",
            "primary_user_query": user_query,
            "secondary_user_query": "",
            "decision_source": "llm",
            "route_reason": f"llm:{response.intent}",
            "last_route_reason": f"llm:{response.intent}",
            "risk_level": risk_level,
            "pending_clarification": "",
            "clarification_target": "",
            "recent_context": recent_context,
            "topic_focus": topic_focus,
            "deferred_user_question": "",
            "clarification_attempts": 0,
            "recommended_department": state.get("recommended_department", ""),
            "appointment_context": state.get("appointment_context", {}),
            "last_appointment_no": state.get("last_appointment_no", ""),
            **pending_updates,
        }

    clarification_attempts = int(state.get("clarification_attempts") or 0) + 1
    if clarification_attempts > 1:
        if _looks_like_medical_request(user_query, conversation_summary=state.get("conversation_summary", ""), recent_context=recent_context, topic_focus=topic_focus):
            fallback_answer = "我先给你一个保守建议：如果你有持续不适、症状加重，建议尽快线下就医；如果你愿意，也可以再补充一句最困扰你的症状，我会继续帮你缩小范围。"
        else:
            fallback_answer = "我先按你现在这句话理解来继续帮你，不再追问太多。如果你愿意，也可以再补充一点背景，我会回答得更贴合。"
        return {
            "intent": "medical_rag",
            "primary_intent": "medical_rag",
            "secondary_intent": "",
            "primary_user_query": user_query,
            "secondary_user_query": "",
            "decision_source": "clarification_budget",
            "route_reason": "clarification_budget_exceeded",
            "last_route_reason": "clarification_budget_exceeded",
            "risk_level": risk_level,
            "pending_clarification": "",
            "clarification_target": "",
            "recent_context": recent_context,
            "topic_focus": topic_focus,
            "deferred_user_question": "",
            "clarification_attempts": clarification_attempts,
            "recommended_department": state.get("recommended_department", ""),
            "appointment_context": state.get("appointment_context", {}),
            "last_appointment_no": state.get("last_appointment_no", ""),
            **_reset_pending_action_if_needed(state),
            "messages": [AIMessage(content=fallback_answer)],
        }

    clarification = response.clarification_needed if response.clarification_needed and len(response.clarification_needed.strip()) > 5 else "可以再具体描述一下你的问题吗？"
    return {
        "intent": "clarification",
        "primary_intent": "clarification",
        "secondary_intent": "",
        "primary_user_query": user_query,
        "secondary_user_query": "",
        "decision_source": "llm",
        "route_reason": "llm:clarification",
        "last_route_reason": "llm:clarification",
        "risk_level": risk_level,
        "pending_clarification": clarification,
        "clarification_target": "intent_router",
        "recent_context": recent_context,
        "topic_focus": topic_focus,
        "deferred_user_question": "",
        "clarification_attempts": clarification_attempts,
        "recommended_department": state.get("recommended_department", ""),
        "appointment_context": state.get("appointment_context", {}),
        "last_appointment_no": state.get("last_appointment_no", ""),
        **_reset_pending_action_if_needed(state),
        "messages": [AIMessage(content=clarification)],
    }


def rewrite_query(state: State, llm):
    last_message = state["messages"][-1]
    conversation_summary = state.get("conversation_summary", "")
    recent_context = state.get("recent_context") or _build_recent_context(state.get("messages", []))
    user_query = state.get("primary_user_query") or str(last_message.content).strip()
    topic_focus = state.get("topic_focus", "")

    if state.get("intent") == "medical_rag" and _looks_like_general_non_medical_query(user_query):
        delete_all = _build_history_reset_messages(state["messages"])
        return {
            "questionIsClear": True,
            "messages": delete_all,
            "originalQuery": user_query,
            "rewrittenQuestions": [user_query],
            "recent_context": recent_context,
            "topic_focus": topic_focus,
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
        }

    context_parts = []
    if conversation_summary.strip():
        context_parts.append(f"Conversation Context:\n{conversation_summary}\n")
    if recent_context.strip():
        context_parts.append(f"Recent Dialogue Context:\n{recent_context}\n")
    if topic_focus.strip():
        context_parts.append(f"Topic focus:\n{topic_focus}\n")
    context_parts.append(f"User Query:\n{user_query}\n")
    context_section = "".join(context_parts)

    llm_with_structure = llm.with_config(temperature=0.1).with_structured_output(QueryAnalysis)
    response = llm_with_structure.invoke([SystemMessage(content=get_rewrite_query_prompt()), HumanMessage(content=context_section)])

    if response.questions and response.is_clear:
        delete_all = _build_history_reset_messages(state["messages"])
        return {
            "questionIsClear": True,
            "messages": delete_all,
            "originalQuery": user_query,
            "rewrittenQuestions": response.questions,
            "recent_context": recent_context,
            "topic_focus": topic_focus,
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
        }

    if _looks_like_department_question(user_query):
        delete_all = _build_history_reset_messages(state["messages"])
        return {
            "questionIsClear": True,
            "messages": delete_all,
            "originalQuery": user_query,
            "rewrittenQuestions": [user_query],
            "recent_context": recent_context,
            "topic_focus": topic_focus,
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
        }

    if state.get("intent") == "medical_rag" and _looks_like_medical_knowledge_question(user_query):
        delete_all = _build_history_reset_messages(state["messages"])
        fallback_query = response.questions[0] if response.questions else user_query
        return {
            "questionIsClear": True,
            "messages": delete_all,
            "originalQuery": user_query,
            "rewrittenQuestions": [fallback_query],
            "recent_context": recent_context,
            "topic_focus": topic_focus,
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
        }

    if state.get("intent") == "medical_rag" and _looks_like_medical_follow_up(user_query, "\n".join(part for part in (conversation_summary, topic_focus) if part), recent_context):
        delete_all = _build_history_reset_messages(state["messages"])
        fallback_query = response.questions[0] if response.questions else f"{topic_focus or recent_context or conversation_summary}\nFollow-up: {user_query}"
        return {
            "questionIsClear": True,
            "messages": delete_all,
            "originalQuery": user_query,
            "rewrittenQuestions": [fallback_query],
            "recent_context": recent_context,
            "topic_focus": topic_focus,
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
        }

    if state.get("intent") == "medical_rag" and state.get("pending_clarification"):
        delete_all = _build_history_reset_messages(state["messages"])
        fallback_query = response.questions[0] if response.questions else (f"{topic_focus or recent_context or conversation_summary}\nQuestion: {user_query}" if (topic_focus or recent_context or conversation_summary) else user_query)
        return {
            "questionIsClear": True,
            "messages": delete_all,
            "originalQuery": user_query,
            "rewrittenQuestions": [fallback_query],
            "recent_context": recent_context,
            "topic_focus": topic_focus,
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
        }

    clarification_attempts = int(state.get("clarification_attempts") or 0) + 1
    if clarification_attempts > 1:
        fallback_query = response.questions[0] if response.questions else (topic_focus or user_query)
        return {
            "questionIsClear": True,
            "messages": _build_history_reset_messages(state["messages"]),
            "originalQuery": user_query,
            "rewrittenQuestions": [fallback_query],
            "recent_context": recent_context,
            "topic_focus": topic_focus or _extract_topic_focus(user_query, topic_focus),
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": clarification_attempts,
        }

    clarification = response.clarification_needed if response.clarification_needed and len(response.clarification_needed.strip()) > 10 else "我可以继续帮你，但还差一点关键信息。你能再具体一点吗？"
    return {
        "questionIsClear": False,
        "recent_context": recent_context,
        "topic_focus": topic_focus or _extract_topic_focus(user_query, topic_focus),
        "pending_clarification": clarification,
        "clarification_target": "rewrite_query",
        "clarification_attempts": clarification_attempts,
        "messages": [AIMessage(content=clarification)],
    }


def plan_retrieval_queries(state: State, llm):
    rewritten = [item for item in (state.get("rewrittenQuestions") or []) if str(item).strip()]
    original_query = state.get("originalQuery") or state.get("primary_user_query") or ""
    recent_context = state.get("recent_context", "")
    topic_focus = state.get("topic_focus", "")
    base_query = rewritten[0] if rewritten else original_query
    fallback_plan = plan_queries(base_query, topic_focus=topic_focus, recent_context=recent_context)

    if not base_query:
        return {"planned_queries": fallback_plan}

    try:
        planner = llm.with_config(temperature=0.1).with_structured_output(RetrievalQueryPlan)
        response = planner.invoke(
            [
                SystemMessage(content=get_retrieval_query_plan_prompt()),
                HumanMessage(
                    content=(
                        f"Original query:\n{original_query}\n\n"
                        f"Rewritten query:\n{base_query}\n\n"
                        f"Recent context:\n{recent_context}\n\n"
                        f"Topic focus:\n{topic_focus}"
                    )
                ),
            ]
        )
        planned = []
        seen = set()
        for item in (response.queries or []) + fallback_plan:
            text = re.sub(r"\s+", " ", str(item or "").strip())
            key = text.lower()
            if not text or key in seen:
                continue
            seen.add(key)
            planned.append(text)
        return {"planned_queries": planned[:4] or fallback_plan}
    except Exception:
        return {"planned_queries": fallback_plan}


def recommend_department(state: State, llm):
    last_message = state["messages"][-1]
    user_query = state.get("primary_user_query") or str(last_message.content).strip()
    conversation_summary = state.get("conversation_summary", "")
    risk_level = state.get("risk_level", "normal")
    topic_focus = state.get("topic_focus", "")

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
                "clarification_attempts": 0,
                "recommended_department": "急诊科",
                "topic_focus": topic_focus or "急诊科",
                "appointment_context": _build_appointment_context(state.get("appointment_context"), {"department": "急诊科"}),
                **_reset_pending_action_if_needed(state),
                "messages": [AIMessage(content=answer)],
            }
        clarification_attempts = int(state.get("clarification_attempts") or 0) + 1
        if clarification_attempts > 1:
            answer = "如果你目前还拿不准具体挂什么科，建议先从 **全科医学科/普通内科** 开始，由医生根据症状再分流；如果出现胸痛、呼吸困难、意识异常等情况，请优先急诊。"
            return {
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": clarification_attempts,
                "recommended_department": "全科医学科",
                "topic_focus": topic_focus or "全科医学科",
                "appointment_context": _build_appointment_context(state.get("appointment_context"), {"department": "全科医学科"}),
                **_reset_pending_action_if_needed(state),
                "messages": [AIMessage(content=answer)],
            }
        clarification = response.clarification_needed if response.clarification_needed and len(response.clarification_needed.strip()) > 5 else "可以再补充一下你的主要症状、持续时间或最不舒服的部位吗？"
        return {
            "pending_clarification": clarification,
            "clarification_target": "recommend_department",
            "clarification_attempts": clarification_attempts,
            "recommended_department": "",
            "topic_focus": topic_focus or _extract_topic_focus(user_query, topic_focus),
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
        "clarification_attempts": 0,
        "topic_focus": response.department.strip(),
        "appointment_context": _build_appointment_context(state.get("appointment_context"), {"department": response.department.strip()}),
        **_clear_pending_action_state(),
        "messages": [AIMessage(content=answer)],
    }


def _handle_appointment_legacy(state: State, llm, appointment_service):
    last_message = state["messages"][-1]
    user_query = state.get("primary_user_query") or str(last_message.content).strip()
    appointment_context = dict(state.get("appointment_context") or {})
    pending_action_type = state.get("pending_action_type", "")
    pending_payload = _sanitize_pending_payload(state.get("pending_action_payload"))

    if pending_action_type == "appointment":
        if _is_abort_request(user_query):
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
                f"- 时段：**{booking['time_slot']}**\n"
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
            "clarification_attempts": int(state.get("clarification_attempts") or 0) + 1,
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
            "clarification_attempts": int(state.get("clarification_attempts") or 0) + 1,
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
                "clarification_attempts": int(state.get('clarification_attempts') or 0) + 1,
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
        **_build_pending_confirmation("appointment", preview_payload),
        "messages": [AIMessage(content=_format_booking_preview(preview_payload))],
    }


def _handle_cancel_appointment_legacy(state: State, llm, appointment_service):
    last_message = state["messages"][-1]
    user_query = state.get("primary_user_query") or str(last_message.content).strip()
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
            "clarification_attempts": int(state.get("clarification_attempts") or 0) + 1,
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
            "我找到了多条可取消预约，请回复具体预约号，或直接说“第 1 个 / 第 2 个”：\n"
            f"{options}"
        )
        return {
            "intent": "cancel_appointment",
            "pending_clarification": clarification,
            "clarification_target": "handle_cancel_appointment",
            "clarification_attempts": int(state.get("clarification_attempts") or 0) + 1,
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
        pass


def _invoke_appointment_skill_request(llm, state: State, user_query: str) -> dict:
    appointment_context = dict(state.get("appointment_context") or {})
    llm_with_tools = llm.with_config(temperature=0.1).bind_tools([AppointmentSkillRequest])
    response = llm_with_tools.invoke(
        [
            SystemMessage(content=get_appointment_skill_prompt()),
            HumanMessage(
                content=(
                    f"Conversation summary:\n{state.get('conversation_summary', '')}\n\n"
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


def handle_appointment_skill(state: State, llm, appointment_service):
    last_message = state["messages"][-1]
    user_query = state.get("primary_user_query") or str(last_message.content).strip()
    appointment_context = dict(state.get("appointment_context") or {})
    pending_action_type = state.get("pending_action_type", "")
    pending_payload = _sanitize_pending_payload(state.get("pending_action_payload"))
    pending_candidates = state.get("pending_candidates", []) or []
    active_intent = state.get("intent") or state.get("primary_intent") or "appointment"
    skill = AppointmentSkill(appointment_service)

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
            booking = skill.confirm_appointment(state["thread_id"], pending_payload)
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
            cancelled = skill.confirm_cancellation(state["thread_id"], pending_payload)
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
                "messages": [AIMessage(content="如果你确认取消这条预约，请直接回复 **确认取消**；如果想取消别的预约，也可以直接告诉我预约号或说“第 1 个 / 第 2 个”。")],
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
            "messages": [AIMessage(content="我还没确定你要取消哪一条。你可以直接回复预约号，或者说“第 1 个 / 第 2 个”。")],
        }

    available_doctors = list(appointment_context.get("available_doctors") or [])
    selected_doctor_name = _pick_doctor_name_from_text(user_query, available_doctors) or appointment_context.get("doctor_name", "")
    if active_intent == "appointment" and available_doctors:
        if _wants_any_available_doctor(user_query):
            chosen_schedule = _sort_schedule_options(available_doctors)[0]
            payload = _schedule_to_preview_payload(chosen_schedule)
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
            "clarification_attempts": int(state.get("clarification_attempts") or 0) + 1,
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
        message, appointments = skill.list_my_appointments(state["thread_id"])
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
                "clarification_attempts": int(state.get("clarification_attempts") or 0) + 1,
                "messages": [AIMessage(content=clarification)],
            }
        schedule_date_value = date.fromisoformat(normalized_date) if normalized_date and time_slot else None
        message, doctor_options = skill.discover_doctors(department, schedule_date=schedule_date_value, time_slot=time_slot)
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
        if doctor_name:
            schedule_date_value = date.fromisoformat(normalized_date) if normalized_date else None
            message, availability = skill.discover_doctor_availability(
                doctor_name,
                department=department,
                schedule_date=schedule_date_value,
                time_slot=time_slot,
            )
            _log_appointment_skill_event(state, skill_mode="discovery", request_type="discover_availability", selected_candidate_count=len(availability), final_action="discover_doctor_availability")
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="discover_availability", topic_focus=department or doctor_name, appointment_context=_build_appointment_context(merged_context, {"available_doctors": availability}), candidates=availability, skill_last_prompt=message),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content=message)],
            }
        if department:
            message, upcoming = skill.discover_department_availability(department)
            _log_appointment_skill_event(state, skill_mode="discovery", request_type="discover_availability", selected_candidate_count=len(upcoming), final_action="discover_department_availability")
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="discover_availability", topic_focus=department, appointment_context=_build_appointment_context(merged_context, {"available_doctors": upcoming}), candidates=upcoming, skill_last_prompt=message),
                "pending_clarification": "",
                "clarification_target": "",
                "clarification_attempts": 0,
                **_clear_pending_action_state(),
                "messages": [AIMessage(content=message)],
            }

    if skill_action == "prepare_reschedule" or any(token in (user_query or "").lower() for token in _RESCHEDULE_HINTS):
        current_items = appointment_service.find_candidate_appointments(
            thread_id=state["thread_id"],
            appointment_no=appointment_no or (state.get("last_appointment_no", "") if _should_use_last_appointment(user_query) else "") or None,
            department=department or None,
            schedule_date=date.fromisoformat(normalized_date) if normalized_date else None,
        )
        if not current_items:
            message = "我暂时没锁定要改约的那条预约。你可以先告诉我预约号，或者说“改最近那个预约”。"
            return {
                **_base_skill_state_update(state, intent="appointment", skill_mode="clarify", appointment_context=merged_context, skill_last_prompt=message),
                "pending_clarification": message,
                "clarification_target": "handle_appointment_skill",
                "clarification_attempts": int(state.get("clarification_attempts") or 0) + 1,
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
        preview, candidates = skill.prepare_cancellation(
            state["thread_id"],
            appointment_no=appointment_no,
            department=department,
            schedule_date=date.fromisoformat(normalized_date) if normalized_date else None,
        )
        if preview:
            payload = preview.__dict__
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
            message = "我找到了多条可取消预约，请回复具体预约号，或直接说“第 1 个 / 第 2 个”：\n" + "\n".join(
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

    if not department:
        clarification = "你想挂哪个科室？如果还不确定，我也可以先根据症状帮你推荐挂什么科。"
        return {
            **_base_skill_state_update(state, intent="appointment", skill_mode="clarify", appointment_context=merged_context, skill_last_prompt=clarification),
            "pending_clarification": clarification,
            "clarification_target": "handle_appointment_skill",
            "clarification_attempts": int(state.get("clarification_attempts") or 0) + 1,
            **_clear_pending_action_state(),
            "messages": [AIMessage(content=clarification)],
        }

    if not normalized_date or not time_slot:
        message, upcoming = skill.discover_department_availability(department)
        _log_appointment_skill_event(state, skill_mode="discovery", request_type="discover_department_availability", selected_candidate_count=len(upcoming), final_action="discover_department_availability")
        return {
            **_base_skill_state_update(state, intent="appointment", skill_mode="discover_availability", topic_focus=department, appointment_context=_build_appointment_context(merged_context, {"available_doctors": upcoming}), candidates=upcoming, skill_last_prompt=message),
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
            **_clear_pending_action_state(),
            "messages": [AIMessage(content=message)],
        }

    preview, doctor_options, alternatives = skill.prepare_appointment(
        department=department,
        schedule_date=date.fromisoformat(normalized_date),
        time_slot=time_slot,
        doctor_name=doctor_name,
        allow_any_doctor=wants_any_doctor,
    )
    if preview:
        payload = preview.__dict__
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


def handle_appointment(state: State, llm, appointment_service):
    merged_state = dict(state)
    merged_state.setdefault("intent", "appointment")
    merged_state.setdefault("primary_intent", "appointment")
    return handle_appointment_skill(merged_state, llm, appointment_service)


def handle_cancel_appointment(state: State, llm, appointment_service):
    merged_state = dict(state)
    merged_state.setdefault("intent", "cancel_appointment")
    merged_state.setdefault("primary_intent", "cancel_appointment")
    return handle_appointment_skill(merged_state, llm, appointment_service)

def request_clarification(state: State):
    return {}


def prepare_secondary_turn(state: State):
    secondary_intent = state.get("secondary_intent", "")
    deferred_question = state.get("deferred_user_question") or state.get("secondary_user_query") or ""
    if not secondary_intent or not deferred_question:
        return {}
    return {
        "intent": secondary_intent,
        "primary_intent": secondary_intent,
        "secondary_intent": "",
        "primary_user_query": deferred_question,
        "secondary_user_query": "",
        "deferred_user_question": "",
        "route_reason": f"resume_secondary:{secondary_intent}",
        "last_route_reason": f"resume_secondary:{secondary_intent}",
        "messages": [HumanMessage(content=deferred_question)],
    }

# --- Agent Nodes ---
def orchestrator(state: AgentState, llm_with_tools):
    context_summary = state.get("context_summary", "").strip()
    recent_context = state.get("recent_context", "").strip()
    topic_focus = state.get("topic_focus", "").strip()
    question = str(state.get("question") or "").strip()
    query_plan = [str(item).strip() for item in (state.get("query_plan") or []) if str(item).strip()]
    is_medical_request = _looks_like_medical_request(
        question,
        conversation_summary=context_summary,
        recent_context=recent_context,
        topic_focus=topic_focus,
    )
    sys_msg = SystemMessage(content=get_orchestrator_prompt())
    summary_injection = (
        [HumanMessage(content=f"[COMPRESSED CONTEXT FROM PRIOR RESEARCH]\n\n{context_summary}")]
        if context_summary else []
    )
    recent_context_injection = (
        [HumanMessage(content=f"[RECENT DIALOGUE CONTEXT]\n\n{recent_context}")]
        if recent_context else []
    )
    topic_focus_injection = (
        [HumanMessage(content=f"[TOPIC FOCUS]\n\n{topic_focus}")]
        if topic_focus else []
    )
    query_plan_injection = (
        [HumanMessage(content="[RETRIEVAL QUERY PLAN]\n\n" + "\n".join(f"- {item}" for item in query_plan))]
        if query_plan else []
    )
    if not state.get("messages"):
        human_msg = HumanMessage(content=question)
        base_messages = [sys_msg] + summary_injection + recent_context_injection + topic_focus_injection + query_plan_injection + [human_msg]
        if is_medical_request:
            retrieval_hint = (
                "For this medical question, call 'search_child_chunks' first unless the injected context already provides enough evidence. "
                "Prefer the current question first; if the first retrieval is weak, you may try one alternate query from the retrieval query plan, but avoid repeating the same search."
            )
            base_messages.append(HumanMessage(content=retrieval_hint))
        response = llm_with_tools.invoke(base_messages)
        return {"messages": [human_msg, response], "tool_call_count": len(response.tool_calls or []), "iteration_count": 1}

    response = llm_with_tools.invoke([sys_msg] + summary_injection + recent_context_injection + topic_focus_injection + query_plan_injection + state["messages"])
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
    recent_context = state.get("recent_context", "").strip()
    topic_focus = state.get("topic_focus", "").strip()
    user_query = str(state.get("question") or "").strip()
    is_medical_request = _looks_like_medical_request(
        user_query,
        conversation_summary=context_summary,
        recent_context=recent_context,
        topic_focus=topic_focus,
    )
    inferred_risk = _infer_risk_level(user_query, "normal")
    risk_level = "high" if _needs_strict_medical_safety(user_query, inferred_risk) else "normal"
    has_no_evidence = any("NO_EVIDENCE" in content for content in unique_contents)

    context_parts = []
    if context_summary:
        context_parts.append(f"## Compressed Research Context (from prior iterations)\n\n{context_summary}")
    if recent_context:
        context_parts.append(f"## Recent Dialogue Context\n\n{recent_context}")
    if unique_contents:
        context_parts.append(
            "## Retrieved Data (current iteration)\n\n" +
            "\n\n".join(f"--- DATA SOURCE {i} ---\n{content}" for i, content in enumerate(unique_contents, 1))
        )

    context_text = "\n\n".join(context_parts) if context_parts else "No data was retrieved from the documents."

    prompt_content = (
        f"USER QUERY: {user_query}\n\n"
        f"REQUEST TYPE: {'medical' if is_medical_request else 'general_or_non_medical'}\n"
        f"RISK LEVEL: {risk_level}\n"
        f"KNOWLEDGE STATUS: {'no_evidence' if has_no_evidence else 'limited_or_partial'}\n\n"
        f"{context_text}\n\n"
        "INSTRUCTION:\n"
        "- If this is a medical request with weak or missing evidence, still provide a concise general medical-information answer when reasonably safe.\n"
        "- For that medical fallback mode, clearly say the answer was not sufficiently based on knowledge-base retrieval and cannot replace in-person medical diagnosis.\n"
        "- For severe symptoms, worsening symptoms, or medication/dosing questions, add a stronger safety reminder.\n"
        "- For non-medical or casual questions, answer naturally and do not force a medical refusal."
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


def _extract_source_citations(messages) -> list[dict]:
    citations = []
    seen = set()
    current_confidence = ""
    current_evidence_score = None
    for message in messages or []:
        if not isinstance(message, ToolMessage):
            continue
        text = str(message.content or "")
        confidence_match = re.search(r"Confidence Bucket:\s*(\w+)", text, re.IGNORECASE)
        if confidence_match and not current_confidence:
            current_confidence = confidence_match.group(1).strip().lower()
        score_match = re.search(r"Score:\s*([0-9]*\.?[0-9]+)", text, re.IGNORECASE)
        if score_match:
            try:
                score_value = float(score_match.group(1))
            except ValueError:
                score_value = None
            if score_value is not None and current_evidence_score is None:
                current_evidence_score = score_value
        for block in text.split("\n\n"):
            title_match = re.search(r"Source Title:\s*(.+)", block)
            source_type_match = re.search(r"Source Type:\s*(.+)", block)
            url_match = re.search(r"Original URL:\s*(.+)", block)
            source_match = re.search(r"File Name:\s*(.+)", block)
            freshness_match = re.search(r"Freshness Bucket:\s*(.+)", block)
            score_match = re.search(r"Score:\s*([0-9]*\.?[0-9]+)", block, re.IGNORECASE)
            if not any((title_match, source_match)):
                continue
            title = (title_match.group(1).strip() if title_match else source_match.group(1).strip())
            source_type = source_type_match.group(1).strip() if source_type_match else "unknown"
            original_url = url_match.group(1).strip() if url_match else ""
            freshness_bucket = freshness_match.group(1).strip().lower() if freshness_match else ""
            evidence_score = current_evidence_score
            if score_match:
                try:
                    evidence_score = float(score_match.group(1))
                except ValueError:
                    pass
            key = (title, source_type, original_url, freshness_bucket)
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                {
                    "title": title,
                    "source_type": source_type,
                    "original_url": original_url,
                    "confidence_bucket": current_confidence or "",
                    "freshness_bucket": freshness_bucket,
                    "evidence_score": evidence_score,
                }
            )
    return citations


def collect_answer(state: AgentState):
    last_message = state["messages"][-1]
    is_valid = isinstance(last_message, AIMessage) and last_message.content and not last_message.tool_calls
    answer = _sanitize_final_answer_text(last_message.content) if is_valid else "Unable to generate an answer."
    citations = _extract_source_citations(state.get("messages", []))
    confidence_bucket = next((item.get("confidence_bucket") for item in citations if item.get("confidence_bucket")), "")
    if not confidence_bucket:
        confidence_bucket = "no_evidence" if any("NO_EVIDENCE" in str(msg.content or "") for msg in state.get("messages", []) if isinstance(msg, ToolMessage)) else "low"
    evidence_scores = [
        float(item.get("evidence_score"))
        for item in citations
        if item.get("evidence_score") is not None
    ]
    return {
        "final_answer": answer,
        "agent_answers": [{
            "index": state["question_index"],
            "question": state["question"],
            "answer": answer,
            "query_plan": state.get("query_plan", []),
            "confidence_bucket": confidence_bucket,
            "evidence_score": max(evidence_scores) if evidence_scores else None,
            "sources": citations[:3],
        }]
    }
# --- End of Agent Nodes---

def grounded_answer_generation(state: State, llm):
    if not state.get("agent_answers"):
        return {"messages": [AIMessage(content="No answers were generated.")]}

    sorted_answers = sorted(state["agent_answers"], key=lambda x: x["index"])

    formatted_answers = ""
    for i, ans in enumerate(sorted_answers, start=1):
        formatted_answers += (f"\nAnswer {i}:\n"f"{ans['answer']}\n")

    user_message = HumanMessage(content=f"""Original user question: {state["originalQuery"]}\nRetrieved answers:{formatted_answers}""")
    synthesis_response = llm.invoke([SystemMessage(content=get_aggregation_prompt()), user_message])
    all_sources = []
    seen_sources = set()
    confidence_levels = []
    evidence_scores = []
    for answer in sorted_answers:
        bucket = str(answer.get("confidence_bucket") or "").strip().lower()
        if bucket:
            confidence_levels.append(bucket)
        score = answer.get("evidence_score")
        if score is not None:
            try:
                evidence_scores.append(float(score))
            except (TypeError, ValueError):
                pass
        for item in answer.get("sources") or []:
            key = (item.get("title", ""), item.get("source_type", ""), item.get("original_url", ""))
            if key in seen_sources:
                continue
            seen_sources.add(key)
            all_sources.append(item)

    confidence_bucket = "high"
    if "no_evidence" in confidence_levels:
        confidence_bucket = "no_evidence"
    elif "low" in confidence_levels:
        confidence_bucket = "low"
    elif "medium" in confidence_levels:
        confidence_bucket = "medium"
    aggregate_evidence_score = max(evidence_scores) if evidence_scores else None

    citation_lines = _format_reference_lines(all_sources)

    original_query = state.get("originalQuery", "")
    is_medical_request = _looks_like_medical_request(
        original_query,
        conversation_summary=state.get("conversation_summary", ""),
        recent_context=state.get("recent_context", ""),
        topic_focus=state.get("topic_focus", ""),
    )
    risk_level = _infer_risk_level(original_query, state.get("risk_level", "normal"))

    confidence_note = ""
    confidence_label = _confidence_bucket_label(confidence_bucket)
    confidence_explanation = _confidence_bucket_explanation(
        confidence_bucket,
        is_medical_request=is_medical_request,
    )
    if is_medical_request and confidence_bucket in {"no_evidence", "low"}:
        confidence_note = f"\n\n证据强度：`{confidence_label}`。{confidence_explanation}\n\n" + _build_medical_fallback_notice(
            risk_level="high" if _needs_strict_medical_safety(original_query, risk_level) else "normal",
            confidence_bucket=confidence_bucket,
        )
    elif confidence_bucket == "medium":
        confidence_note = f"\n\n证据强度：`{confidence_label}`。{confidence_explanation}"
    elif confidence_bucket == "high":
        confidence_note = f"\n\n证据强度：`{confidence_label}`。{confidence_explanation}"
    if any(item.get("freshness_bucket") == "outdated" for item in all_sources):
        confidence_note += "\n\n版本提醒：当前命中了较旧资料，请结合最新指南或线下医生意见一起判断。"

    citation_block = ""
    if citation_lines:
        citation_block = "\n\n参考来源：\n" + "\n".join(citation_lines)

    final_content = _sanitize_final_answer_text(synthesis_response.content)
    return {
        "messages": [AIMessage(content=f"{final_content}{confidence_note}{citation_block}")],
        "clarification_attempts": 0,
        "grounding_evidence_score": aggregate_evidence_score,
    }


def answer_grounding_check(state: State, llm):
    latest_message = state["messages"][-1] if state.get("messages") else None
    current_answer = str(getattr(latest_message, "content", "") or "").strip()
    confidence_levels = [
        str(item.get("confidence_bucket") or "").strip().lower()
        for item in state.get("agent_answers") or []
        if str(item.get("confidence_bucket") or "").strip()
    ]
    evidence_score = state.get("grounding_evidence_score")
    pseudo_docs = []
    if evidence_score is not None:
        try:
            pseudo_docs = [Document(page_content="", metadata={"score": float(evidence_score)})]
        except (TypeError, ValueError):
            pseudo_docs = []
    if not pseudo_docs:
        if "no_evidence" in confidence_levels:
            pseudo_docs = []
        elif "low" in confidence_levels:
            pseudo_docs = [Document(page_content="", metadata={"score": 0.68})]
        else:
            pseudo_docs = [Document(page_content="", metadata={"score": 0.88})]
    original_query = state.get("originalQuery", "")
    risk_level = _infer_risk_level(original_query, state.get("risk_level", "normal"))
    grounded = ground_answer(
        current_answer,
        pseudo_docs,
        question=original_query,
        medical_mode=_looks_like_medical_request(
            original_query,
            conversation_summary=state.get("conversation_summary", ""),
            recent_context=state.get("recent_context", ""),
            topic_focus=state.get("topic_focus", ""),
        ),
        high_risk=_needs_strict_medical_safety(original_query, risk_level),
    )
    final_answer = _strip_leading_query_plan_blob(grounded.get("revised_answer", current_answer))
    if final_answer == current_answer:
        return {}
    return {"messages": [AIMessage(content=final_answer)]}


def aggregate_answers(state: State, llm):
    return grounded_answer_generation(state, llm)
