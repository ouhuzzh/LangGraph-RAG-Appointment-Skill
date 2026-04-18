from typing import Literal
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Send
from .graph_state import State, AgentState
from config import MAX_ITERATIONS, MAX_TOOL_CALLS

def route_after_intent(state: State) -> Literal["rewrite_query", "recommend_department", "handle_appointment", "handle_cancel_appointment", "request_clarification", "__end__"]:
    intent = state.get("intent", "")
    if intent == "greeting":
        return "__end__"
    if intent == "triage":
        return "recommend_department"
    if intent == "appointment":
        return "handle_appointment"
    if intent == "cancel_appointment":
        return "handle_cancel_appointment"
    if intent == "clarification":
        return "request_clarification"
    return "rewrite_query"


def route_after_rewrite(state: State) -> Literal["request_clarification", "agent"]:
    if not state.get("questionIsClear", False):
        return "request_clarification"
    else:
        summary = state.get("conversation_summary", "")
        recent_context = state.get("recent_context", "")
        topic_focus = state.get("topic_focus", "")
        return [
                Send("agent", {"question": query, "question_index": idx, "messages": [], "context_summary": summary, "recent_context": recent_context, "topic_focus": topic_focus})
                for idx, query in enumerate(state["rewrittenQuestions"])
            ]


def route_after_clarification(state: State) -> Literal["intent_router", "rewrite_query", "recommend_department", "handle_appointment", "handle_cancel_appointment"]:
    target = state.get("clarification_target", "") or "intent_router"
    if target == "rewrite_query":
        return "rewrite_query"
    if target == "recommend_department":
        return "recommend_department"
    if target == "handle_appointment":
        return "handle_appointment"
    if target == "handle_cancel_appointment":
        return "handle_cancel_appointment"
    return "intent_router"


def route_after_orchestrator_call(state: AgentState) -> Literal["tools", "fallback_response", "collect_answer"]:
    iteration = state.get("iteration_count", 0)
    tool_count = state.get("tool_call_count", 0)

    if iteration >= MAX_ITERATIONS or tool_count > MAX_TOOL_CALLS:
        return "fallback_response"

    if _has_repeated_no_evidence(state) or _has_repeated_search_query(state):
        return "fallback_response"

    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []

    if not tool_calls:
        return "collect_answer"
    
    return "tools"


def route_after_action(state: State) -> Literal["prepare_secondary_turn", "__end__"]:
    if state.get("secondary_intent") and state.get("deferred_user_question") and not state.get("pending_clarification") and not state.get("pending_action_type"):
        return "prepare_secondary_turn"
    return "__end__"


def route_after_prepare_secondary_turn(state: State) -> Literal["rewrite_query", "handle_appointment", "handle_cancel_appointment", "recommend_department"]:
    intent = state.get("primary_intent") or state.get("intent") or ""
    if intent == "appointment":
        return "handle_appointment"
    if intent == "cancel_appointment":
        return "handle_cancel_appointment"
    if intent == "triage":
        return "recommend_department"
    return "rewrite_query"


def _has_repeated_no_evidence(state: AgentState) -> bool:
    tool_messages = [msg for msg in state.get("messages", []) if isinstance(msg, ToolMessage)]
    if len(tool_messages) < 2:
        return False
    last_two_contents = [str(msg.content or "") for msg in tool_messages[-2:]]
    return all("NO_EVIDENCE" in content for content in last_two_contents)


def _has_repeated_search_query(state: AgentState) -> bool:
    queries = []
    for msg in reversed(state.get("messages", [])):
        if not isinstance(msg, AIMessage):
            continue
        tool_calls = getattr(msg, "tool_calls", None) or []
        for tool_call in tool_calls:
            if tool_call.get("name") != "search_child_chunks":
                continue
            query = str((tool_call.get("args") or {}).get("query") or "").strip().lower()
            if query:
                queries.append(query)
            if len(queries) >= 2:
                return queries[0] == queries[1]
    return False
