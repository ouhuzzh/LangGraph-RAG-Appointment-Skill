import logging
import sys
import uuid
from pathlib import Path
from typing import Iterable

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

import config
from api.dependencies import get_container
from api.schemas import (
    ChatHistoryResponse,
    ChatMessage,
    ChatStreamRequest,
    ChatSseEvent,
    ClearSessionRequest,
    ClearSessionResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    KnowledgeBaseStatusResponse,
    SystemStatusResponse,
)


logger = logging.getLogger(__name__)


def _event_payload(event: ChatSseEvent) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


def _visible_assistant_text(chunk) -> str:
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


def _message_from_langchain(message) -> ChatMessage | None:
    content = str(getattr(message, "content", "") or "").strip()
    if not content:
        return None
    if isinstance(message, HumanMessage):
        return ChatMessage(role="user", content=content)
    if isinstance(message, AIMessage):
        return ChatMessage(role="assistant", content=content)
    if isinstance(message, SystemMessage):
        return ChatMessage(role="system", content=content)
    return None


def _stream_chat_events(thread_id: str, message: str) -> Iterable[str]:
    container = get_container()
    final_content = ""
    yield _event_payload(ChatSseEvent(type="session", thread_id=thread_id, content=thread_id))
    try:
        with container.chat_lock:
            for chunk in container.chat_interface.chat(message, [], reveal_diagnostics=False, thread_id=thread_id):
                content = _visible_assistant_text(chunk)
                if not content:
                    continue
                final_content = content
                yield _event_payload(ChatSseEvent(type="message", thread_id=thread_id, content=content))
        yield _event_payload(ChatSseEvent(type="final", thread_id=thread_id, content=final_content, done=True))
    except Exception as exc:
        logger.exception("API chat stream failed for thread_id=%s", thread_id)
        yield _event_payload(
            ChatSseEvent(
                type="app-error",
                thread_id=thread_id,
                content="聊天服务暂时不可用，请稍后再试。",
                error=str(exc),
                done=True,
            )
        )


def create_app() -> FastAPI:
    app = FastAPI(title="Medical Agentic Assistant API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.API_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.post("/api/chat/session", response_model=CreateSessionResponse)
    def create_session(payload: CreateSessionRequest | None = Body(default=None)):
        thread_id = (payload.thread_id if payload else None) or uuid.uuid4().hex
        return CreateSessionResponse(thread_id=thread_id)

    @app.get("/api/system/status", response_model=SystemStatusResponse)
    def system_status():
        container = get_container()
        system = container.rag_system.get_system_status()
        knowledge = container.rag_system.get_knowledge_base_status()
        return SystemStatusResponse(
            state=system["state"],
            message=system["message"],
            last_error=system.get("last_error") or "",
            steps=system.get("steps") or {},
            knowledge_base=KnowledgeBaseStatusResponse(
                status=knowledge["status"],
                message=knowledge["message"],
                last_error=knowledge.get("last_error") or "",
                stats=knowledge.get("stats") or {},
            ),
        )

    @app.get("/api/chat/history", response_model=ChatHistoryResponse)
    def chat_history(thread_id: str = Query(..., min_length=1)):
        container = get_container()
        messages = []
        for item in container.rag_system.session_memory.get_recent_messages(thread_id):
            converted = _message_from_langchain(item)
            if converted:
                messages.append(converted)
        return ChatHistoryResponse(thread_id=thread_id, messages=messages)

    @app.post("/api/chat/clear", response_model=ClearSessionResponse)
    def clear_chat(payload: ClearSessionRequest):
        container = get_container()
        container.chat_interface.clear_session(payload.thread_id)
        return ClearSessionResponse(thread_id=payload.thread_id)

    @app.get("/api/chat/stream")
    def chat_stream(
        thread_id: str = Query(..., min_length=1),
        message: str = Query(..., min_length=1),
    ):
        if not message.strip():
            raise HTTPException(status_code=400, detail="message is required")
        return StreamingResponse(
            _stream_chat_events(thread_id, message.strip()),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/chat/stream")
    def chat_stream_post(payload: ChatStreamRequest):
        if not payload.message.strip():
            raise HTTPException(status_code=400, detail="message is required")
        return StreamingResponse(
            _stream_chat_events(payload.thread_id, payload.message.strip()),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
