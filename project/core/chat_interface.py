import json
import re

import config
from langchain_core.messages import HumanMessage, AIMessage, AIMessageChunk, ToolMessage, SystemMessage

SILENT_NODES = {"rewrite_query", "intent_router"}
SYSTEM_NODES = {"summarize_history", "rewrite_query"}
APPOINTMENT_UPDATE_HINTS = ("改", "换", "预约", "挂号", "医生", "科", "时间", "时段")
CANCEL_UPDATE_HINTS = ("取消", "退号", "预约号", "第", "appointment", "cancel")
PENDING_ACK_HINTS = ("可以", "好的", "行", "好", "ok", "okay")

SYSTEM_NODE_CONFIG = {
    "rewrite_query":     {"title": "🔍 Query Analysis & Rewriting"},
    "summarize_history": {"title": "📋 Chat History Summary"},
}

# --- Helpers ---

def make_message(content, *, title=None, node=None):
    msg = {"role": "assistant", "content": content}
    if title or node:
        msg["metadata"] = {k: v for k, v in {"title": title, "node": node}.items() if v}
    return msg


def find_msg_idx(messages, node):
    return next(
        (i for i, m in enumerate(messages) if m.get("metadata", {}).get("node") == node),
        None,
    )


def parse_rewrite_json(buffer):
    match = re.search(r"\{.*\}", buffer, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except Exception:
        return None


def format_rewrite_content(buffer):
    data = parse_rewrite_json(buffer)
    if not data:
        return "⏳ Analyzing query..."
    if data.get("is_clear"):
        lines = ["✅ **Query is clear**"]
        if data.get("questions"):
            lines += ["\n**Rewritten queries:**"] + [f"- {q}" for q in data["questions"]]
    else:
        lines = ["❓ **Query is unclear**"]
        clarification = data.get("clarification_needed", "")
        if clarification and clarification.strip().lower() != "no":
            lines.append(f"\nClarification needed: *{clarification}*")
    return "\n".join(lines)

# --- End of Helpers ---

class ChatInterface:

    def __init__(self, rag_system):
        self.rag_system = rag_system

    def _handle_system_node(self, chunk, node, response_messages, system_node_buffer):
        """Update (or create) the collapsible system-node message and surface any clarification."""
        system_node_buffer[node] = system_node_buffer.get(node, "") + chunk.content
        buffer = system_node_buffer[node]
        title  = SYSTEM_NODE_CONFIG[node]["title"]
        content = format_rewrite_content(buffer) if node == "rewrite_query" else buffer

        idx = find_msg_idx(response_messages, node)
        if idx is None:
            response_messages.append(make_message(content, title=title, node=node))
        else:
            response_messages[idx]["content"] = content

        if node == "rewrite_query":
            self._surface_clarification(buffer, response_messages)

    def _surface_clarification(self, buffer, response_messages):
        """If the query is unclear, add/update a plain clarification message."""
        data          = parse_rewrite_json(buffer) or {}
        clarification = data.get("clarification_needed", "")
        if not data.get("is_clear") and clarification.strip().lower() not in ("", "no"):
            cidx = find_msg_idx(response_messages, "clarification")
            if cidx is None:
                response_messages.append(make_message(clarification, node="clarification"))
            else:
                response_messages[cidx]["content"] = clarification

    def _handle_tool_call(self, chunk, response_messages, active_tool_calls):
        """Register new tool calls as collapsible messages."""
        for tc in chunk.tool_calls:
            if tc.get("id") and tc["id"] not in active_tool_calls:
                response_messages.append(
                    make_message(f"Running `{tc['name']}`...", title=f"🛠️ {tc['name']}")
                )
                active_tool_calls[tc["id"]] = len(response_messages) - 1

    def _handle_tool_result(self, chunk, response_messages, active_tool_calls):
        """Fill in the tool result inside the matching collapsible message."""
        idx = active_tool_calls.get(chunk.tool_call_id)
        if idx is not None:
            preview = str(chunk.content)[:300]
            suffix  = "\n..." if len(str(chunk.content)) > 300 else ""
            response_messages[idx]["content"] = f"```\n{preview}{suffix}\n```"

    def _handle_llm_token(self, chunk, node, response_messages):
        """Append streaming LLM tokens to the last plain assistant message."""
        last = response_messages[-1] if response_messages else None
        if not (last and last.get("role") == "assistant" and "metadata" not in last):
            response_messages.append(make_message(""))
        response_messages[-1]["content"] += chunk.content

    @staticmethod
    def _extract_final_assistant_text(response_messages):
        for message in reversed(response_messages):
            if message.get("role") == "assistant" and "metadata" not in message and message.get("content", "").strip():
                return message["content"].strip()
        return ""

    @staticmethod
    def _extract_latest_state_assistant(latest_values):
        for message in reversed(latest_values.get("messages", []) or []):
            if isinstance(message, AIMessage):
                content = str(message.content or "").strip()
                if content and not getattr(message, "tool_calls", None):
                    return content
        return ""

    @staticmethod
    def _extract_clarification_text(response_messages):
        for message in reversed(response_messages):
            if message.get("metadata", {}).get("node") == "clarification":
                content = message.get("content", "").strip()
                if content:
                    return content
        return ""

    @staticmethod
    def _looks_like_department_question(query: str) -> bool:
        normalized = (query or "").strip().lower()
        patterns = [
            "挂什么科",
            "挂哪个科",
            "看什么科",
            "看哪个科",
            "挂哪科",
            "看哪科",
            "咨询什么科",
            "which department",
            "what department should i visit",
            "what department should i register for",
        ]
        return any(pattern in normalized for pattern in patterns)

    @staticmethod
    def _looks_like_schedule_update(query: str) -> bool:
        normalized = (query or "").strip().lower()
        if any(token in normalized for token in APPOINTMENT_UPDATE_HINTS):
            return True
        return bool(re.search(r"\d{1,2}[点时:：]", normalized) or re.search(r"\d{1,2}\s*月|\d{4}-\d{1,2}-\d{1,2}|明天|后天|周[一二三四五六日天]", normalized))

    @staticmethod
    def _should_continue_pending_intent(user_message: str, existing_state: dict) -> bool:
        normalized = (user_message or "").strip().lower()
        pending_action_type = existing_state.get("pending_action_type", "")
        pending_candidates = existing_state.get("pending_candidates") or []
        if pending_action_type:
            if any(word in normalized for word in ("确认预约", "确认挂号", "确认取消", "确认退号", "先不用", "不用了", "算了", "放弃")):
                return True
            if normalized in PENDING_ACK_HINTS:
                return True
            if pending_candidates and (re.search(r"\bapt[a-z0-9]+\b", normalized, re.IGNORECASE) or re.search(r"第\s*[1-9]\d*", normalized)):
                return True
            if pending_action_type == "appointment":
                return ChatInterface._looks_like_schedule_update(user_message)
            if pending_action_type == "cancel_appointment":
                return any(token in normalized for token in CANCEL_UPDATE_HINTS)

        pending_clarification = existing_state.get("pending_clarification")
        current_intent = existing_state.get("intent", "")
        if not pending_clarification or not current_intent:
            return False
        if current_intent == "appointment":
            return ChatInterface._looks_like_schedule_update(user_message) or len(normalized) <= 20
        if current_intent == "cancel_appointment":
            return any(token in normalized for token in CANCEL_UPDATE_HINTS) or len(normalized) <= 20
        if current_intent == "triage":
            return len(normalized) <= 30 and not any(token in normalized for token in ("是什么", "怎么办", "为什么"))
        return False

    @staticmethod
    def _infer_intent(user_message: str, existing_state: dict):
        if ChatInterface._should_continue_pending_intent(user_message, existing_state or {}):
            return existing_state.get("pending_action_type") or existing_state.get("intent", "clarification")

        normalized = (user_message or "").strip().lower()
        # 问候语
        greetings = ["你好", "您好", "hello", "hi", "谢谢", "感谢", "thanks", "再见", "bye"]
        if len(normalized) <= 15 and any(g in normalized for g in greetings):
            return "greeting"
        # 科室问题优先(与 intent_router 一致)
        if ChatInterface._looks_like_department_question(user_message):
            return "triage"
        has_appointment = any(keyword in normalized for keyword in ["挂号", "预约", "book appointment", "register"])
        has_cancel = any(keyword in normalized for keyword in ["取消", "退号", "cancel appointment", "cancel booking"])
        if has_appointment:
            return "appointment"
        if has_cancel:
            return "cancel_appointment"
        return "medical_rag"

    @staticmethod
    def _infer_risk_level(user_message: str, existing_state: dict):
        normalized = (user_message or "").strip().lower()
        if any(keyword.lower() in normalized for keyword in config.HIGH_RISK_KEYWORDS):
            return "high"
        return existing_state.get("risk_level", "normal")

    @staticmethod
    def _build_state_messages(session_state: dict):
        if not session_state:
            return []

        parts = []
        if session_state.get("intent"):
            parts.append(f"Active intent: {session_state['intent']}")
        if session_state.get("risk_level"):
            parts.append(f"Risk level: {session_state['risk_level']}")
        if session_state.get("pending_clarification"):
            parts.append(f"Pending clarification: {session_state['pending_clarification']}")
        if session_state.get("recommended_department"):
            parts.append(f"Recommended department: {session_state['recommended_department']}")
        if session_state.get("appointment_context"):
            parts.append(f"Appointment context: {session_state['appointment_context']}")
        if session_state.get("last_appointment_no"):
            parts.append(f"Last appointment number: {session_state['last_appointment_no']}")
        if session_state.get("pending_action_type"):
            parts.append(f"Pending action type: {session_state['pending_action_type']}")
        if session_state.get("pending_action_payload"):
            parts.append(f"Pending action payload: {session_state['pending_action_payload']}")
        if session_state.get("pending_candidates"):
            parts.append(f"Pending candidates: {session_state['pending_candidates']}")

        if not parts:
            return []

        return [SystemMessage(content="Conversation state context:\n" + "\n".join(parts))]

    def chat(self, message, history):
        """Generator that streams Gradio chat message dicts."""
        if not self.rag_system.agent_graph:
            readiness_getter = getattr(self.rag_system, "get_readiness_message", None)
            if callable(readiness_getter):
                yield readiness_getter()
            else:
                yield "系统正在准备中，请稍后再试。"
            return

        graph_config  = self.rag_system.get_config()
        current_state = self.rag_system.agent_graph.get_state(graph_config)
        thread_id     = self.rag_system.thread_id
        user_message  = message.strip()
        session_state = self.rag_system.session_memory.get_state(thread_id)
        inferred_intent = self._infer_intent(user_message, session_state or {})

        if inferred_intent == "medical_rag" and not self.rag_system.vector_db.has_documents():
            knowledge_status_getter = getattr(self.rag_system, "get_knowledge_base_status", None)
            knowledge_status = knowledge_status_getter() if callable(knowledge_status_getter) else {}
            status = knowledge_status.get("status")
            if status == "building":
                yield "知识库正在后台补建中，医学知识类问题稍后再试会更准确。预约/取消功能现在仍然可以正常使用。"
            elif status == "failed":
                detail = knowledge_status.get("last_error", "")
                extra = f" 失败原因：{detail}" if detail else ""
                yield f"知识库补建失败，暂时没法回答文档型/知识库型问题。{extra}"
            elif status == "no_documents":
                yield "当前还没有本地文档可供索引，暂时没法回答文档型/知识库型问题。你可以先到 Documents 页上传 PDF 或 Markdown，再回来提问。"
            else:
                yield "当前知识库里还没有可检索文档，系统会继续尝试补建。你也可以先到 Documents 页检查文档状态。"
            return

        try:
            if current_state.next:
                self.rag_system.agent_graph.update_state(graph_config, {"messages": [HumanMessage(content=user_message)], "thread_id": thread_id})
                stream_input = None
            else:
                stored_messages = []
                stored_messages = self.rag_system.session_memory.get_recent_messages(thread_id)
                long_term_summary = self.rag_system.summary_store.get_summary(thread_id)
                state_messages = self._build_state_messages(session_state)
                if long_term_summary:
                    self.rag_system.agent_graph.update_state(
                        graph_config,
                        {"conversation_summary": long_term_summary},
                    )
                if session_state:
                    self.rag_system.agent_graph.update_state(
                        graph_config,
                        {
                            "thread_id": thread_id,
                            "intent": session_state.get("intent", ""),
                            "risk_level": session_state.get("risk_level", "normal"),
                            "pending_clarification": session_state.get("pending_clarification") or "",
                            "recommended_department": session_state.get("recommended_department") or "",
                            "appointment_context": session_state.get("appointment_context") or {},
                            "last_appointment_no": session_state.get("last_appointment_no") or "",
                            "pending_action_type": session_state.get("pending_action_type") or "",
                            "pending_action_payload": session_state.get("pending_action_payload") or {},
                            "pending_confirmation_id": session_state.get("pending_confirmation_id") or "",
                            "pending_candidates": session_state.get("pending_candidates") or [],
                        },
                    )
                if not session_state:
                    self.rag_system.agent_graph.update_state(graph_config, {"thread_id": thread_id})
                stream_input = {"messages": [*state_messages, *stored_messages, HumanMessage(content=user_message)]}

            response_messages  = []

            for chunk, metadata in self.rag_system.agent_graph.stream(stream_input, config=graph_config, stream_mode="messages"):
                node = metadata.get("langgraph_node", "")

                if isinstance(chunk, AIMessageChunk) and chunk.content and node not in SILENT_NODES and node not in SYSTEM_NODES:
                    self._handle_llm_token(chunk, node, response_messages)

                yield response_messages

            final_assistant = self._extract_final_assistant_text(response_messages)
            clarification_text = self._extract_clarification_text(response_messages)
            latest_state = self.rag_system.agent_graph.get_state(graph_config)
            latest_values = getattr(latest_state, "values", {}) or {}
            if not final_assistant:
                final_from_state = self._extract_latest_state_assistant(latest_values)
                if final_from_state:
                    response_messages.append(make_message(final_from_state))
                    final_assistant = final_from_state
                    yield response_messages
            if final_assistant:
                recent_count = self.rag_system.session_memory.append_exchange(thread_id, user_message, final_assistant)
                if recent_count >= config.SUMMARY_REFRESH_THRESHOLD:
                    conversation_summary = latest_values.get("conversation_summary", "")
                    if conversation_summary:
                        self.rag_system.summary_store.save_summary(thread_id, conversation_summary, recent_count)

            if "intent" in latest_values:
                resolved_intent = latest_values.get("intent")
            else:
                resolved_intent = inferred_intent

            if "risk_level" in latest_values:
                resolved_risk_level = latest_values.get("risk_level")
            else:
                resolved_risk_level = self._infer_risk_level(user_message, session_state)

            if "pending_clarification" in latest_values:
                resolved_pending = latest_values.get("pending_clarification") or None
            else:
                resolved_pending = clarification_text or None

            if "recommended_department" in latest_values:
                resolved_department = latest_values.get("recommended_department") or None
            else:
                resolved_department = session_state.get("recommended_department")

            if "appointment_context" in latest_values:
                resolved_appointment_context = latest_values.get("appointment_context") or {}
            else:
                resolved_appointment_context = session_state.get("appointment_context") or {}

            if "last_appointment_no" in latest_values:
                resolved_last_appointment_no = latest_values.get("last_appointment_no") or None
            else:
                resolved_last_appointment_no = session_state.get("last_appointment_no")

            if "pending_action_type" in latest_values:
                resolved_pending_action_type = latest_values.get("pending_action_type") or ""
            else:
                resolved_pending_action_type = session_state.get("pending_action_type") or ""

            if "pending_action_payload" in latest_values:
                resolved_pending_action_payload = latest_values.get("pending_action_payload") or {}
            else:
                resolved_pending_action_payload = session_state.get("pending_action_payload") or {}

            if "pending_confirmation_id" in latest_values:
                resolved_pending_confirmation_id = latest_values.get("pending_confirmation_id") or ""
            else:
                resolved_pending_confirmation_id = session_state.get("pending_confirmation_id") or ""

            if "pending_candidates" in latest_values:
                resolved_pending_candidates = latest_values.get("pending_candidates") or []
            else:
                resolved_pending_candidates = session_state.get("pending_candidates") or []

            updated_state = {
                "intent": resolved_intent,
                "risk_level": resolved_risk_level,
                "pending_clarification": resolved_pending,
                "recommended_department": resolved_department,
                "appointment_context": resolved_appointment_context,
                "last_appointment_no": resolved_last_appointment_no,
                "pending_action_type": resolved_pending_action_type,
                "pending_action_payload": resolved_pending_action_payload,
                "pending_confirmation_id": resolved_pending_confirmation_id,
                "pending_candidates": resolved_pending_candidates,
            }
            if updated_state != (session_state or {}):
                self.rag_system.session_memory.set_state(thread_id, updated_state)

        except Exception as e:
            yield f"❌ Error: {str(e)}"

    def clear_session(self):
        self.rag_system.reset_thread()
        self.rag_system.observability.flush()
