import uuid

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from api.dependencies import get_container
from api.schemas import (
    ChatHistoryResponse,
    ChatMessage,
    ChatStreamRequest,
    ClearSessionRequest,
    ClearSessionResponse,
    CreateSessionRequest,
    CreateSessionResponse,
)
from api.sse import stream_chat_events


router = APIRouter()


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


@router.post("/api/chat/session", response_model=CreateSessionResponse)
def create_session(payload: CreateSessionRequest | None = Body(default=None)):
    thread_id = (payload.thread_id if payload else None) or uuid.uuid4().hex
    return CreateSessionResponse(thread_id=thread_id)


@router.get("/api/chat/history", response_model=ChatHistoryResponse)
def chat_history(thread_id: str = Query(..., min_length=1)):
    container = get_container()
    messages = []
    for item in container.rag_system.session_memory.get_recent_messages(thread_id):
        converted = _message_from_langchain(item)
        if converted:
            messages.append(converted)
    return ChatHistoryResponse(thread_id=thread_id, messages=messages)


@router.post("/api/chat/clear", response_model=ClearSessionResponse)
def clear_chat(payload: ClearSessionRequest):
    container = get_container()
    container.chat_interface.clear_session(payload.thread_id)
    return ClearSessionResponse(thread_id=payload.thread_id)


@router.get("/api/chat/stream")
def chat_stream(
    thread_id: str = Query(..., min_length=1),
    message: str = Query(..., min_length=1),
):
    if not message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    return StreamingResponse(
        stream_chat_events(thread_id, message.strip()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/chat/stream")
def chat_stream_post(payload: ChatStreamRequest):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    return StreamingResponse(
        stream_chat_events(payload.thread_id, payload.message.strip()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
