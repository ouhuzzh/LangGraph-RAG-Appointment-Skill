from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class CreateSessionRequest(BaseModel):
    thread_id: str | None = None


class CreateSessionResponse(BaseModel):
    thread_id: str


class ChatHistoryResponse(BaseModel):
    thread_id: str
    messages: list[ChatMessage] = Field(default_factory=list)


class ClearSessionRequest(BaseModel):
    thread_id: str


class ClearSessionResponse(BaseModel):
    thread_id: str
    cleared: bool = True


class ChatStreamRequest(BaseModel):
    thread_id: str
    message: str


class KnowledgeBaseStatusResponse(BaseModel):
    status: str
    message: str
    last_error: str = ""
    stats: dict[str, Any] = Field(default_factory=dict)


class SystemStatusResponse(BaseModel):
    state: str
    message: str
    last_error: str = ""
    steps: dict[str, Any] = Field(default_factory=dict)
    knowledge_base: KnowledgeBaseStatusResponse


class ChatSseEvent(BaseModel):
    type: Literal["session", "status", "message", "final", "app-error"]
    thread_id: str
    content: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    done: bool = False
    error: str = ""
