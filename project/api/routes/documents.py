import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from api.dependencies import get_container
from api.schemas import (
    DocumentItem,
    DocumentListResponse,
    DocumentStatusResponse,
    DocumentTaskListResponse,
    DocumentUploadResponse,
    KnowledgeBaseStatusResponse,
    OfficialSyncRequest,
    OfficialSyncResponse,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


def _knowledge_response(container) -> KnowledgeBaseStatusResponse:
    knowledge = container.rag_system.get_knowledge_base_status()
    return KnowledgeBaseStatusResponse(
        status=knowledge["status"],
        message=knowledge["message"],
        last_error=knowledge.get("last_error") or "",
        stats=knowledge.get("stats") or {},
    )


def _recent_tasks(container) -> list[dict]:
    stats = container.rag_system.get_knowledge_base_status().get("stats") or {}
    return list(stats.get("recent_imports") or [])


def _safe_upload_name(filename: str) -> str:
    name = Path(filename or "").name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    return name


@router.get("/status", response_model=DocumentStatusResponse)
def documents_status():
    container = get_container()
    return DocumentStatusResponse(
        knowledge_base=_knowledge_response(container),
        recent_tasks=_recent_tasks(container),
    )


@router.get("/list", response_model=DocumentListResponse)
def documents_list():
    container = get_container()
    document_manager = container.document_manager
    items = []
    for path in document_manager.get_markdown_paths():
        stat = path.stat()
        items.append(
            DocumentItem(
                name=path.name,
                file_type=path.suffix.lstrip(".") or "md",
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            )
        )
    return DocumentListResponse(documents=items)


@router.get("/tasks", response_model=DocumentTaskListResponse)
def documents_tasks():
    container = get_container()
    return DocumentTaskListResponse(tasks=_recent_tasks(container))


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_documents(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="请选择要上传的文件")

    container = get_container()
    upload_dir = Path("runtime") / "api_uploads" / uuid.uuid4().hex
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved_paths = []
    try:
        for file in files:
            filename = _safe_upload_name(file.filename or "")
            target = upload_dir / filename
            with target.open("wb") as buffer:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    buffer.write(chunk)
            saved_paths.append(target)

        report = container.document_manager.add_documents_with_report(saved_paths)
        sync_event = report.get("sync_event")
        if sync_event:
            container.rag_system.record_import_event(sync_event)
        container.rag_system.refresh_knowledge_base_status()
        container.rag_system.start_knowledge_base_bootstrap()
        return DocumentUploadResponse(
            message=(
                f"已处理 {report.get('processed', 0)} 个文件：新增 {report.get('added', 0)}，"
                f"更新 {report.get('updated', 0)}，未变化 {report.get('unchanged', 0)}，"
                f"失败 {report.get('failed', 0)}。"
            ),
            report=report,
        )
    except Exception as exc:
        logger.exception("Document upload failed")
        raise HTTPException(status_code=500, detail=f"文档上传处理失败：{exc}") from exc
    finally:
        shutil.rmtree(upload_dir, ignore_errors=True)


@router.post("/sync-official", response_model=OfficialSyncResponse)
def sync_official_documents(payload: OfficialSyncRequest):
    container = get_container()
    try:
        result = container.document_manager.sync_official_source(
            source=payload.source,
            limit=payload.limit,
            trigger_type="manual",
        )
        event = result.to_event()
        container.rag_system.record_import_event(event)
        container.rag_system.refresh_knowledge_base_status()
        container.rag_system.start_knowledge_base_bootstrap()
        return OfficialSyncResponse(
            message=(
                f"官方同步完成：新增 {result.written}，更新 {result.updated}，"
                f"下线 {result.deactivated}，未变化 {result.unchanged}。"
            ),
            result=event,
        )
    except Exception as exc:
        logger.exception("Official document sync failed for source=%s", payload.source)
        raise HTTPException(status_code=500, detail=f"官方资料同步失败：{exc}") from exc
