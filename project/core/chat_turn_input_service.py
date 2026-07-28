"""Build LangGraph inputs for one chat turn."""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass

import config
from core.context_compression import trim_messages_to_token_budget
from langchain_core.messages import HumanMessage
from utils import estimate_context_tokens


logger = logging.getLogger(__name__)

# Strip emoji characters that can break LLM structured-output parsing.
_EMOJI_PATTERN = re.compile(
    '[\U0001F600-\U0001F64F'   # emoticons
    '\U0001F300-\U0001F5FF'   # symbols & pictographs
    '\U0001F680-\U0001F6FF'   # transport & map symbols
    '\U0001F1E0-\U0001F1FF'   # flags
    '\U00002702-\U000027B0'
    '\U0001F900-\U0001F9FF'   # supplemental symbols
    '\U0001FA00-\U0001FA6F'
    '\U0001FA70-\U0001FAFF'
    '\U00002600-\U000026FF'
    ']+',
    flags=re.UNICODE,
)


@dataclass
class ChatTurnInput:
    active_thread_id: str
    graph_config: dict
    current_state: object
    user_message: str
    request_id: str
    session_state: dict
    checkpoint_resumed: bool
    user_id: str
    user_memories_text: str
    stream_input: dict | None
    early_response: str | None = None


# ---------------------------------------------------------------------------
# Prompt injection detection patterns
# ---------------------------------------------------------------------------
_INJECTION_MARKERS = [
    "忽略之前的", "忽略上面的", "ignore previous", "ignore above",
    "forget your", "忘记你的",
]
_SYSTEM_LEVEL_REQUESTS = [
    "系统提示词", "system prompt", "你的指令", "your instructions",
    "你的设定", "初始设定",
]
_ROLE_HIJACK_PATTERNS = [
    "你现在是", "you are now", "act as", "假装你是",
]

_PROMPT_INJECTION_WARNING = (
    "您的消息似乎包含特殊指令，请直接描述您的健康问题，我会尽力帮助您。"
)
_EMOJI_ONLY_WARNING = (
    "您的消息似乎只包含表情符号，请用文字描述您的健康问题，我来帮您分析。"
)
_SYMBOL_ONLY_WARNING = (
    "您输入的内容似乎包含一些特殊符号，请描述您的健康问题，我会尽力帮助您。"
)


def _detect_prompt_injection(text: str) -> bool:
    """Return True when the text looks like a prompt-injection attempt.

    Only fires when an injection marker AND (a system-level request OR a role
    hijack pattern) are both present, to avoid false positives on normal
    medical queries.
    """
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    has_injection_marker = any(marker in normalized for marker in _INJECTION_MARKERS)
    if not has_injection_marker:
        return False
    has_system_request = any(req in normalized for req in _SYSTEM_LEVEL_REQUESTS)
    has_role_hijack = any(pat in normalized for pat in _ROLE_HIJACK_PATTERNS)
    return has_system_request or has_role_hijack


def _is_pure_symbol_input(text: str) -> bool:
    """Return True when text contains no letters and no CJK characters."""
    if not text:
        return True
    return not re.search(r'[a-zA-Z\u4e00-\u9fff]', text)


class ChatTurnInputService:
    def __init__(
        self,
        rag_system,
        *,
        get_graph_config,
        fetch_user_memories,
        build_state_messages,
        graph_state_from_session,
    ):
        self.rag_system = rag_system
        self._get_graph_config = get_graph_config
        self._fetch_user_memories = fetch_user_memories
        self._build_state_messages = build_state_messages
        self._graph_state_from_session = graph_state_from_session

    def prepare(self, *, message: str, thread_id: str | None = None) -> ChatTurnInput:
        active_thread_id = thread_id or self.rag_system.thread_id
        graph_config = self._get_graph_config(active_thread_id)
        current_state = self.rag_system.agent_graph.get_state(graph_config)
        user_message = message.strip()
        # Remove emoji; fall back to original text if stripping yields empty string.
        _stripped = _EMOJI_PATTERN.sub('', user_message).strip()
        if _stripped:
            user_message = _stripped

        # --- 1.4 Emoji-only / pure-symbol early return ---
        early_response = None
        if not _stripped:
            # Input was pure emoji
            early_response = _EMOJI_ONLY_WARNING
        elif _is_pure_symbol_input(_stripped):
            # Input has no letters or CJK characters (only punctuation/symbols)
            early_response = _SYMBOL_ONLY_WARNING

        # --- 1.2 Prompt injection detection ---
        if early_response is None and _detect_prompt_injection(user_message):
            early_response = _PROMPT_INJECTION_WARNING

        request_id = uuid.uuid4().hex
        session_state = self.rag_system.session_memory.get_state(active_thread_id)
        checkpoint_resumed = bool(current_state.next)

        # A stale clarification interrupt must not swallow a fresh greeting. When the
        # graph is paused awaiting a clarification answer (interrupt_before=
        # [request_clarification]) and the user sends a pure greeting instead, they
        # have abandoned that flow — blindly resuming would feed "你好" in as the
        # answer ("请补充要预约的日期。"). Drop the stale checkpoint + leaked session
        # state (visible message history in session_memory is preserved) so the
        # greeting is handled as a fresh turn by analyze_turn's greeting short-circuit.
        if checkpoint_resumed and self._is_pure_greeting(user_message):
            try:
                self.rag_system.agent_graph.checkpointer.delete_thread(active_thread_id)
                self.rag_system.session_memory.set_state(active_thread_id, {})
            except Exception:
                logger.warning("Failed to clear stale interrupt for greeting; continuing", exc_info=True)
            current_state = self.rag_system.agent_graph.get_state(graph_config)
            session_state = {}
            checkpoint_resumed = False

        user_id = self._resolve_user_id(active_thread_id)
        user_memories_text = self._resolve_user_memories(
            user_id=user_id,
            user_message=user_message,
            active_thread_id=active_thread_id,
        )
        stream_input = self._prepare_stream_input(
            active_thread_id=active_thread_id,
            graph_config=graph_config,
            current_state=current_state,
            user_message=user_message,
            request_id=request_id,
            session_state=session_state,
            user_id=user_id,
            user_memories_text=user_memories_text,
        )

        return ChatTurnInput(
            active_thread_id=active_thread_id,
            graph_config=graph_config,
            current_state=current_state,
            user_message=user_message,
            request_id=request_id,
            session_state=session_state,
            checkpoint_resumed=checkpoint_resumed,
            user_id=user_id,
            user_memories_text=user_memories_text,
            stream_input=stream_input,
            early_response=early_response,
        )

    @staticmethod
    def _is_pure_greeting(user_message: str) -> bool:
        try:
            from rag_agent.node_helpers import _looks_like_greeting
            return _looks_like_greeting(user_message)
        except Exception:
            return False

    def _resolve_user_id(self, active_thread_id: str) -> str:
        if not config.USER_MEMORY_ENABLED:
            return ""
        try:
            chat_sessions = getattr(self.rag_system, "chat_sessions", None)
            if chat_sessions is None:
                return ""
            session_info = chat_sessions.get_session(active_thread_id)
            return (session_info or {}).get("owner_user_id", "") or ""
        except Exception:
            logger.warning("Failed to resolve user_id for memory injection", exc_info=True)
            return ""

    def _resolve_user_memories(self, *, user_id: str, user_message: str, active_thread_id: str) -> str:
        if not (user_id and config.USER_MEMORY_ENABLED and config.USER_MEMORY_INJECTION_ENABLED):
            return ""
        return self._fetch_user_memories(
            user_id=user_id,
            user_message=user_message,
            thread_id=active_thread_id,
        )

    def _prepare_stream_input(
        self,
        *,
        active_thread_id: str,
        graph_config,
        current_state,
        user_message: str,
        request_id: str,
        session_state: dict,
        user_id: str,
        user_memories_text: str,
    ) -> dict | None:
        if current_state.next:
            update_payload = {
                "messages": [HumanMessage(content=user_message)],
                "thread_id": active_thread_id,
                "request_id": request_id,
            }
            if user_memories_text:
                update_payload["user_memories"] = user_memories_text
            self.rag_system.agent_graph.update_state(graph_config, update_payload)
            return None

        stored_messages = self.rag_system.session_memory.get_recent_messages(active_thread_id)
        long_term_summary = self.rag_system.summary_store.get_summary(active_thread_id)
        state_messages = self._build_state_messages(session_state)
        user_message_obj = HumanMessage(content=user_message)

        # Hard-trim safety net: if the full context window is approaching the
        # model limit, drop older stored messages while preserving recent turns.
        candidate_messages = [*state_messages, *stored_messages, user_message_obj]
        if estimate_context_tokens(candidate_messages) > config.CONTEXT_HARD_TRIM_THRESHOLD:
            available_tokens = max(
                0,
                config.CONTEXT_HARD_TRIM_THRESHOLD
                - config.CONTEXT_HARD_TRIM_RESERVE
                - estimate_context_tokens(state_messages)
                - estimate_context_tokens([user_message_obj]),
            )
            stored_messages = trim_messages_to_token_budget(
                stored_messages,
                available_tokens,
                config.RECENT_CONTEXT_TURNS,
            )

        if long_term_summary:
            self.rag_system.agent_graph.update_state(
                graph_config,
                {"conversation_summary": long_term_summary},
            )
        if session_state:
            self.rag_system.agent_graph.update_state(
                graph_config,
                self._graph_state_from_session(active_thread_id, session_state),
            )
        if not session_state:
            self.rag_system.agent_graph.update_state(
                graph_config,
                {"thread_id": active_thread_id, "agent_answers": [{"__reset__": True}]},
            )

        return {
            "messages": [*state_messages, *stored_messages, HumanMessage(content=user_message)],
            "request_id": request_id,
            "user_memories": user_memories_text,
            "user_id": user_id,
        }
