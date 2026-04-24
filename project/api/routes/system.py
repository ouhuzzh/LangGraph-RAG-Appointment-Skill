from fastapi import APIRouter

from api.dependencies import get_container
from api.schemas import KnowledgeBaseStatusResponse, SystemStatusResponse


router = APIRouter()


@router.get("/api/health")
def health():
    return {"ok": True}


@router.get("/api/system/status", response_model=SystemStatusResponse)
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
