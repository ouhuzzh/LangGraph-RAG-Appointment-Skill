# FastAPI API Layer

`project/api/` 是 React 用户端的协议适配层。它不实现 RAG、预约、记忆或知识库同步的核心逻辑，只负责把 HTTP/SSE 请求转换成核心服务调用。

## 文件职责

- `app.py`：创建 FastAPI app、注册 CORS 和路由。
- `dependencies.py`：维护进程内单例容器，复用 `RAGSystem`、`ChatInterface`、`DocumentManager`。
- `schemas.py`：定义前端可见 DTO，避免直接暴露 LangGraph 内部状态。
- `routes/chat.py`：会话创建、历史读取、清空会话、SSE 聊天流。
- `routes/system.py`：健康检查和系统/知识库状态。
- `routes/documents.py`：知识库状态、文档列表、官方来源覆盖度、上传和官方同步。

## 设计原则

- API 返回用户可理解字段，不返回 pending payload、raw graph state 等内部结构。
- 危险操作默认不暴露到 React 前台，例如清空知识库仍留在 Gradio 后台。
- Documents API 只做用户友好的管理能力，高级诊断仍由 Gradio 承担。
- 所有业务行为必须复用 `project/core`、`project/rag_agent`、`project/services`。

## 主要接口

- `POST /api/chat/session`
- `GET /api/chat/history`
- `POST /api/chat/clear`
- `GET /api/chat/stream`
- `GET /api/system/status`
- `GET /api/documents/status`
- `GET /api/documents/list`
- `GET /api/documents/tasks`
- `GET /api/documents/sources`
- `POST /api/documents/upload`
- `POST /api/documents/sync-official`
