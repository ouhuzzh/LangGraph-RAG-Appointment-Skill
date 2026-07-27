"""Routing and turn-analysis nodes.

Intent classification, compound-request splitting, department recommendation,
and conversation summarisation live here.  Private helpers that are only used
by these public nodes are kept local to this module; cross-cutting helpers are
imported from ``node_helpers``.
"""

import logging

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from .graph_state import State
from .schemas import (
    IntentAnalysis,
    build_intent_analysis_schema,
    DepartmentRecommendation,
)
from .prompts import get_conversation_summary_prompt, get_intent_router_prompt, get_department_recommendation_prompt
from .node_helpers import (
    _APPOINTMENT_NO_RE,
    _DEPARTMENT_HINTS,
    _ORDINAL_RE,
    _build_appointment_context,
    _build_recent_context,
    _clear_pending_action_state,
    collect_skill_hints,
    _extract_topic_focus,
    _get_user_query,
    _infer_risk_level,
    _is_abort_request,
    _is_explicit_confirmation,
    _looks_like_department_question,
    _looks_like_explicit_appointment_intent,
    _looks_like_explicit_cancel_intent,
    _looks_like_greeting,
    _looks_like_medical_knowledge_question,
    _looks_like_medical_request,
    _looks_like_medication_risk_query,
    _next_clarification_attempt,
    _normalize_date,
    _normalize_time_slot,
    _pick_candidate_from_text,
    _reset_pending_action_if_needed,
    _starts_with_polite_decline,
    _structured_output_llm,
)


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Local constants
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Private helpers (only used by routing nodes)
# ---------------------------------------------------------------------------

def _user_has_mcp_tools() -> bool:
    """Check if MCP is enabled and at least one server is configured."""
    try:
        import config
        if not config.MCP_ENABLED:
            return False
        from mcp_integration.mcp_server_registry import MCPServerRegistry
        registry = MCPServerRegistry()
        servers = registry.list_all()
        return len(servers) > 0
    except Exception:
        return False


def _needs_medication_detail_clarification(query: str) -> bool:
    normalized = (query or "").strip().lower()
    vague_reference = any(token in normalized for token in ("这个药", "这药", "这种药", "它"))
    return vague_reference and _looks_like_medication_risk_query(query)


def _looks_like_department_name_only(user_query: str) -> bool:
    normalized = (user_query or "").strip()
    if not normalized:
        return False
    return any(department in normalized for department in _DEPARTMENT_HINTS)


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
    # Short queries that contain medical signals are NOT clarification
    if len(normalized) <= 40:
        return not _looks_like_medical_request(user_query)
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


def _classify_query_pipeline(
    user_query: str,
    *,
    conversation_summary: str = "",
    recent_context: str = "",
    topic_focus: str = "",
) -> tuple[str, float, str]:
    """Three-tier intent classification pipeline via skill registry.

    L1: registry.classify_by_keywords() — exact keyword match on skill.keywords
    L2: registry-provided embedding centroids — semantic similarity match
    L3: (caller's responsibility) LLM classification

    Returns (intent, confidence, source) where source is one of:
        "l1_keyword" | "l2_embedding" | "need_llm"
    """
    try:
        from skills.registry import get_skill_registry
        registry = get_skill_registry()
        if not registry.skills:
            return ("", 0.0, "need_llm")

        # L1: keyword-based classification (aggregated from all skills)
        kw_match = registry.classify_by_keywords(user_query)
        if kw_match:
            intent, source = kw_match
            return (intent, 1.0, source)

        # L2: embedding semantic matching (utterances from all skills)
        try:
            from .intent_embedder import get_intent_embedder
            embedder = get_intent_embedder()
            result = embedder.classify(user_query)
            if result is not None:
                intent, confidence = result
                return (intent, confidence, "l2_embedding")
        except Exception:
            pass
    except Exception:
        pass

    return ("", 0.0, "need_llm")


def _classify_query_by_rules(
    user_query: str,
    *,
    conversation_summary: str = "",
    recent_context: str = "",
    topic_focus: str = "",
) -> tuple[str, str]:
    """Backward-compatible wrapper — delegates to L1 keyword matching.

    Prefer _classify_query_pipeline() for new code (returns 3-tuple with confidence).
    This wrapper is kept for existing callers (e.g. tests).
    """
    try:
        from skills.registry import get_skill_registry
        registry = get_skill_registry()
        kw_match = registry.classify_by_keywords(user_query)
        if kw_match:
            return kw_match
    except Exception:
        pass
    return ("", "rule_inconclusive")


def classify_query_offline(query: str, *, conversation_summary: str = "", topic_focus: str = "") -> dict:
    """Offline route classification (L1/L2 only) for benchmarking/eval.

    analyze_turn defers to the LLM turn planner, which can't run offline, so
    offline route metrics use the L1/L2 classifier directly - the same
    classifier the planner consults for L1 hints. Returns a route_result dict
    matching analyze_turn's shape; an inconclusive result defaults to
    medical_rag (the compiled graph's inconclusive -> rewrite_query path).
    """
    intent, conf, reason = _classify_query_pipeline(
        query, conversation_summary=conversation_summary, recent_context="", topic_focus=topic_focus,
    )
    if not intent:
        return {
            "primary_intent": "medical_rag",
            "secondary_intent": "",
            "decision_source": "graph_default",
            "route_reason": "rule_inconclusive_default_rag",
            "intent_confidence": 0.0,
        }
    return {
        "primary_intent": intent,
        "secondary_intent": "",
        "decision_source": reason,
        "route_reason": reason,
        "intent_confidence": float(conf),
    }


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


_STRONG_BOOKING_CUES = (
    "改到", "换到", "改成", "换成", "改约", "换个时间", "换时间",
    "预约", "挂号", "退号", "确认", "取消预约",
)

_QUESTION_MARKERS = ("什么", "怎么", "怎样", "如何", "为什么", "会不会", "能不能", "是不是", "吗", "呢")


def _is_incidental_phrasing(normalized: str) -> bool:
    """Long or question-shaped sentences carry weak cues incidentally.

    Genuine slot-filling replies are short imperatives ("换个医生吧",
    "book Dr.Zhang tomorrow"); "医生说高血压要注意什么" is a topic switch
    that merely happens to contain 医生. Length is script-aware: word count
    for ASCII-dominant text, character count for CJK."""
    if "?" in normalized or "？" in normalized:
        return True
    if any(marker in normalized for marker in _QUESTION_MARKERS):
        return True
    ascii_chars = sum(1 for ch in normalized if ord(ch) < 128)
    if ascii_chars > len(normalized) * 0.7:
        return len(normalized.split()) > 5
    return len(normalized) > 10


def _should_continue_pending_action(state: State, user_query: str) -> bool:
    # Bug 2 fix: "谢谢我不用了" is a polite decline, NOT an abort/cancel
    if _starts_with_polite_decline(user_query):
        return False

    pending_action_type = state.get("pending_action_type", "")
    pending_candidates = state.get("pending_candidates", []) or []
    if not pending_action_type and not pending_candidates:
        return False
    if _is_explicit_confirmation(user_query, pending_action_type):
        return True
    if pending_candidates and _pick_candidate_from_text(user_query, pending_candidates):
        return True

    normalized = (user_query or "").strip().lower()
    has_strong_cue = any(cue in normalized for cue in _STRONG_BOOKING_CUES)

    if _is_abort_request(user_query):
        # Abort words are short interjections. Inside a longer sentence with
        # no booking noun they are incidental ("那我先不吃阿司匹林了可以吗"
        # must NOT cancel the pending booking).
        if has_strong_cue or len(normalized) <= 8 or "约" in normalized or "号" in normalized:
            return True
        return False

    if pending_action_type == "appointment":
        if not _looks_like_appointment_update(user_query):
            return False
        if has_strong_cue:
            return True
        # Weak cues only (医生/时间/今天...): require slot-filling shape.
        return not _is_incidental_phrasing(normalized)
    if pending_action_type == "cancel_appointment":
        if not _looks_like_cancel_update(user_query):
            return False
        strong_cancel = (
            "取消预约" in normalized
            or "退号" in normalized
            or "预约号" in normalized
            or bool(_APPOINTMENT_NO_RE.search(user_query or ""))
            or bool(_ORDINAL_RE.search(user_query or ""))
        )
        if strong_cancel:
            return True
        return not _is_incidental_phrasing(normalized)
    return False


# ---------------------------------------------------------------------------
# Public routing nodes
# ---------------------------------------------------------------------------

def _llm_arbiter_says_continuation(state: State, user_query: str, recent_context: str = "") -> bool:
    """Narrow-band LLM arbiter (opt-in): consulted only for short, signal-free
    replies while an action is pending — "行，就他了" carries no keyword any
    rule can see. Long or question-shaped input never reaches the LLM (topic
    switch by shape). Routing power only; execution stays code-gated."""
    import config as _config
    if not getattr(_config, "ENABLE_LLM_CONTINUATION_ARBITER", False):
        return False
    normalized = (user_query or "").strip().lower()
    if not normalized or _is_incidental_phrasing(normalized):
        return False
    try:
        from .continuation_arbiter import judge_continuation
        return judge_continuation(
            state.get("pending_action_type", ""),
            state.get("pending_action_payload") or {},
            user_query,
            recent_context=recent_context or state.get("recent_context", ""),
        )
    except Exception:
        logger.debug("Continuation arbiter unavailable", exc_info=True)
        return False


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

    # Pending stale exit: if user has a pending action but keeps talking about
    # unrelated topics, auto-clear after 2 consecutive irrelevant turns.
    pending_stale_next = 0
    continuation_reason = ""
    if state.get("pending_action_type"):
        if _should_continue_pending_action(state, user_query):
            continuation_reason = "continue_pending_action"
        elif _llm_arbiter_says_continuation(state, user_query, recent_context):
            continuation_reason = "continue_pending_action_llm"
    if state.get("pending_action_type") and not continuation_reason:
        stale = int(state.get("pending_stale_count", 0)) + 1
        if stale >= 2:
            clear = _clear_pending_action_state()
            clear["pending_stale_count"] = 0
            return {
                "recent_context": recent_context,
                "topic_focus": topic_focus or state.get("topic_focus", ""),
                "primary_intent": "",
                "secondary_intent": "",
                "primary_user_query": user_query,
                "secondary_user_query": "",
                "deferred_user_question": "",
                "decision_source": "llm",
                "route_reason": "pending_stale_exit",
                "last_route_reason": "pending_stale_exit",
                **_clear_pending_action_state(),
                "pending_stale_count": 0,
                "messages": [AIMessage(content="好的，先不管之前的预约。你需要什么帮助？")],
            }
        # Not stale yet — persist the incremented counter so the second
        # consecutive irrelevant turn actually triggers the exit above.
        # (A previous version computed `stale` but never wrote it back,
        # leaving the auto-clear permanently unreachable.)
        pending_stale_next = stale

    if continuation_reason:
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
            "route_reason": continuation_reason,
            "last_route_reason": continuation_reason,
            "pending_stale_count": 0,
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
            "pending_stale_count": 0,
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
            "pending_stale_count": 0,
        }

    if (
        (state.get("intent") == "appointment" or state.get("appointment_skill_mode") in {"discover_department", "clarify", "discover_doctor", "discover_availability"})
        and _looks_like_department_name_only(user_query)
        and not _looks_like_explicit_cancel_intent(user_query)
    ):
        return {
            "recent_context": recent_context,
            "topic_focus": topic_focus or state.get("topic_focus", ""),
            "primary_intent": "appointment",
            "secondary_intent": "",
            "primary_user_query": user_query,
            "secondary_user_query": "",
            "deferred_user_question": "",
            "decision_source": "resume",
            "route_reason": "continue_department_selection",
            "last_route_reason": "continue_department_selection",
            "pending_stale_count": 0,
        }

    # The unified turn planner decomposes every fresh turn (arbitrary connectors,
    # 3+ segments, any intent combo) into planned_tasks. Resume branches above
    # still take precedence. route_after_analyze_turn sends fresh queries
    # (primary_intent empty) to plan_tasks.
    return {
        "recent_context": recent_context,
        "topic_focus": topic_focus or state.get("topic_focus", ""),
        "primary_intent": "",
        "primary_user_query": user_query,
        "originalQuery": user_query,
        "decision_source": "planner",
        "route_reason": "turn_planner",
        "last_route_reason": "turn_planner",
        "intent_source": "planner",
        "pending_stale_count": pending_stale_next,
    }


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

    # Fast-path: very short query with no conversation context → default to medical_rag
    # rather than hitting the LLM with an empty context (147s timeout on 7B).
    summary = state.get("conversation_summary", "") or ""
    has_context = bool(summary.strip() or recent_context.strip() or topic_focus.strip())
    if not has_context and len(user_query.strip()) <= 5 and not _looks_like_greeting(user_query):
        logger.debug("Short query without context, defaulting to medical_rag: %r", user_query[:20])
        return {
            "intent": "medical_rag",
            "primary_intent": "medical_rag",
            "secondary_intent": "",
            "primary_user_query": user_query,
            "secondary_user_query": "",
            "decision_source": "rule_fast_path",
            "route_reason": "short_query_no_context_default_rag",
            "last_route_reason": "short_query_no_context_default_rag",
        }

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

    # Short-circuit: if analyze_turn (or skill registry) already determined a
    # non-empty intent, use it directly.  Skill-registered intents like
    # "mcp_hospital" are NOT in the LLM's intent list — letting the LLM
    # override them would route back to the wrong handler.
    if primary_intent and primary_intent not in ("medical_rag", ""):
        return {
            "intent": primary_intent,
            "primary_intent": primary_intent,
            "secondary_intent": secondary_intent or "",
            "primary_user_query": primary_user_query,
            "secondary_user_query": secondary_user_query or "",
            "decision_source": decision_source or "rule",
            "route_reason": route_reason,
            "last_route_reason": route_reason,
            "risk_level": risk_level,
            "pending_clarification": "",
            "clarification_target": "",
            "recent_context": recent_context,
            "topic_focus": topic_focus,
            "deferred_user_question": state.get("deferred_user_question", "") or secondary_user_query or "",
            "clarification_attempts": 0,
            "recommended_department": state.get("recommended_department", ""),
            "appointment_context": state.get("appointment_context", {}),
            "last_appointment_no": state.get("last_appointment_no", ""),
        }

    try:
        # Collect skill L3 hints and intent labels for dynamic schema + prompt
        skill_hints, intent_labels = collect_skill_hints()

        # Build dynamic schema with Literal[intent_labels] if available
        schema_cls = build_intent_analysis_schema(intent_labels) if intent_labels else IntentAnalysis
        llm_with_structure = _structured_output_llm(llm, schema_cls, temperature=0.1)
        user_memories_section = ""
        if state.get("user_memories"):
            user_memories_section = f"\nKnown user context:\n{state['user_memories']}\n"
        response = llm_with_structure.invoke(
            [
                SystemMessage(content=get_intent_router_prompt(skill_hints)),
                HumanMessage(
                    content=(
                        f"Conversation summary:\n{state.get('conversation_summary', '')}\n\n"
                        f"Recent dialogue context:\n{recent_context}\n"
                        f"{user_memories_section}"
                        f"\nUser query:\n{user_query}"
                    )
                ),
            ]
        )
    except Exception:
        logger.exception("Intent router structured output failed; falling back to medical_rag.")
        return {
            "intent": "medical_rag",
            "primary_intent": "medical_rag",
            "secondary_intent": "",
            "primary_user_query": user_query,
            "secondary_user_query": "",
            "decision_source": "llm_error_fallback",
            "route_reason": "intent_router_exception_fallback",
            "last_route_reason": "intent_router_exception_fallback",
            "risk_level": risk_level,
            "pending_clarification": "",
            "clarification_target": "",
            "recent_context": recent_context,
            "topic_focus": topic_focus or _extract_topic_focus(user_query, topic_focus),
            "deferred_user_question": "",
            "clarification_attempts": 0,
            "recommended_department": state.get("recommended_department", ""),
            "appointment_context": state.get("appointment_context", {}),
            "last_appointment_no": state.get("last_appointment_no", ""),
            **_reset_pending_action_if_needed(state),
        }

    if response.is_clear:
        # Check if the intent is routable — via skill registry or legacy core set
        _valid_intents = {"medical_rag", "triage", "appointment",
                          "cancel_appointment", "greeting", "clarification"}
        try:
            from skills.registry import get_skill_registry
            _valid_intents.update(get_skill_registry().get_route_mapping().keys())
        except Exception:
            pass
        if response.intent in _valid_intents:
            if response.intent == "greeting":
                greeting_msg = "你好！我是你的医疗助手，可以帮你：\n- 🏥 推荐就诊科室\n- 📅 预约挂号\n- ❌ 取消预约\n- 💊 解答医疗健康问题\n\n请问有什么可以帮你的？"
                return {
                    "intent": "greeting",
                    "primary_intent": "greeting",
                    "secondary_intent": "",
                    "primary_user_query": user_query,
                    "secondary_user_query": "",
                    "decision_source": "llm",
                    "route_reason": "llm:greeting",
                    "last_route_reason": "llm:greeting",
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
                    "messages": [AIMessage(content=greeting_msg)],
                }
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

    clarification_attempts = _next_clarification_attempt(state)
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


def recommend_department(state: State, llm):
    user_query = _get_user_query(state)
    conversation_summary = state.get("conversation_summary", "")
    # Re-infer risk from the CURRENT query instead of trusting checkpointed
    # state: clarification-resume routes reach this node directly (bypassing
    # intent_router, the only other re-inference point), so a red-flag reply
    # like "突然胸痛喘不上气" must still trigger the emergency bypass even when
    # the stored risk_level is a stale "normal". Additive: can only raise risk.
    risk_level = _infer_risk_level(user_query, state.get("risk_level", "normal"))
    topic_focus = state.get("topic_focus", "")

    # Bug 5 fix: high-risk symptoms → emergency department FIRST, skip LLM
    if risk_level == "high":
        import json as _json
        answer = (
            "⚠️ **高风险提醒**\n\n"
            "你描述的症状包含需要紧急评估的高风险信号。\n\n"
            "**建议立即前往急诊科就诊**，不要因等待科室匹配而延误。\n\n"
            "如果症状持续加重，请拨打 120 或前往最近的医院急诊。\n\n"
            "---\n"
            "以下是根据你的描述给出的科室参考（不替代急诊判断）："
        )
        # Still give a department recommendation via LLM for reference,
        # but the emergency warning is the PRIMARY message
        try:
            user_memories_section = ""
            if state.get("user_memories"):
                user_memories_section = f"\nKnown user context:\n{state['user_memories']}\n"
            raw_response = llm.with_config(temperature=0.1).invoke(
                [
                    SystemMessage(content=get_department_recommendation_prompt()),
                    HumanMessage(content=f"Conversation summary:\n{conversation_summary}\n{user_memories_section}\nUser query:\n{user_query}"),
                ]
            )
            raw_text = str(raw_response.content or "").strip()
            import re as _re
            json_match = _re.search(r"\{.*\}", raw_text, _re.DOTALL)
            if json_match:
                parsed = _json.loads(json_match.group())
                dept = str(parsed.get("department", "")).strip()
                reason = str(parsed.get("reason", "")).strip()
                if dept:
                    answer += f"\n\n建议科室：**{dept}**\n原因：{reason}"
        except Exception:
            pass

        return {
            "recommended_department": "急诊科",
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
            "topic_focus": topic_focus or "急诊科",
            "appointment_context": _build_appointment_context(state.get("appointment_context"), {"department": "急诊科"}),
            **_clear_pending_action_state(),
            "messages": [AIMessage(content=answer)],
        }

    try:
        user_memories_section = ""
        if state.get("user_memories"):
            user_memories_section = f"\nKnown user context:\n{state['user_memories']}\n"
        raw_response = llm.with_config(temperature=0.1).invoke(
            [
                SystemMessage(content=get_department_recommendation_prompt()),
                HumanMessage(content=f"Conversation summary:\n{conversation_summary}\n{user_memories_section}\nUser query:\n{user_query}"),
            ]
        )
        raw_text = str(raw_response.content or "").strip()
        # Parse JSON from LLM response (supports both raw JSON and markdown code blocks)
        import re
        import json
        json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON found in response")
        parsed = json.loads(json_match.group())
        response = DepartmentRecommendation(
            department=str(parsed.get("department", "")).strip(),
            reason=str(parsed.get("reason", "")).strip(),
            needs_clarification=bool(parsed.get("needs_clarification", False)),
            clarification_needed=str(parsed.get("clarification_needed", "")).strip(),
        )
    except Exception:
        logger.exception("Department recommendation structured output failed; returning safe fallback.")
        answer = "我暂时无法稳定判断最合适的科室。若症状较急或明显加重，建议优先急诊；一般不适可以先到全科医学科/普通内科，由医生再进一步分诊。"
        return {
            "pending_clarification": "",
            "clarification_target": "",
            "clarification_attempts": 0,
            "recommended_department": "全科医学科",
            "topic_focus": topic_focus or "全科医学科",
            "appointment_context": _build_appointment_context(state.get("appointment_context"), {"department": "全科医学科"}),
            **_reset_pending_action_if_needed(state),
            "messages": [AIMessage(content=answer)],
        }

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
        clarification_attempts = _next_clarification_attempt(state)
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


def request_clarification(state: State):
    """No-op node that runs on resume after a clarification interrupt.

    Only executes on resume because the graph is compiled with
    interrupt_before=["request_clarification"], so the fresh-turn entry point
    (reset_turn_state) does not run on resume.
    """
    return {}


__all__ = [
    "analyze_turn",
    "intent_router",
    "recommend_department",
    "request_clarification",
    "summarize_history",
]
