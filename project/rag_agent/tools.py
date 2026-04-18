from contextvars import ContextVar
from typing import List

import config
from langchain_core.tools import tool
from langchain_core.documents import Document
from db.parent_store_manager import ParentStoreManager


_SOURCE_TYPE_PRIORITY = {
    "patient_education": 0,
    "public_health": 1,
    "clinical_guideline": 2,
    "research_article": 3,
}
_DEFAULT_LAYERED_SOURCE_TYPES = ["patient_education", "public_health", "clinical_guideline"]
_NO_EVIDENCE_RESPONSE = "NO_EVIDENCE: 知识库中暂无相关信息，请直接说明未找到相关证据，不要补全答案。"
_RRF_K = 60
_RETRIEVAL_CONTEXT = ContextVar("retrieval_context", default={})
_QUERY_TYPE_KEYWORDS = {
    "public_health": (
        "预防", "风险", "流行", "发病率", "传播", "疫苗", "筛查", "risk", "prevention",
        "incidence", "prevalence", "outbreak", "vaccine", "screening", "public health",
    ),
    "clinical_guideline": (
        "指南", "诊疗方案", "规范", "标准", "共识", "第十版", "剂量", "用法", "首选药",
        "protocol", "guideline", "criteria", "dose", "dosing", "first-line", "recommendation",
    ),
    "patient_education": (
        "是什么", "怎么办", "会不会", "症状", "表现", "原因", "怎么治疗", "怎么缓解", "严重吗",
        "what is", "symptom", "symptoms", "what should", "how to", "can it", "is it serious",
    ),
}


def set_retrieval_context(*, thread_id: str = "", original_query: str = ""):
    return _RETRIEVAL_CONTEXT.set(
        {
            "thread_id": str(thread_id or "").strip(),
            "original_query": str(original_query or "").strip(),
        }
    )


def reset_retrieval_context(token):
    if token is not None:
        _RETRIEVAL_CONTEXT.reset(token)


def get_retrieval_context() -> dict:
    value = _RETRIEVAL_CONTEXT.get()
    return dict(value) if isinstance(value, dict) else {}


def _confidence_bucket(results: List[Document]) -> str:
    if not results:
        return "no_evidence"
    top_doc = results[0]
    metadata = top_doc.metadata or {}
    score = float(metadata.get("rerank_score") or metadata.get("fusion_score") or metadata.get("score") or 0.0)
    if score >= 0.85 and len(results) >= 2:
        return "high"
    if score >= 0.72:
        return "medium"
    return "low"


class ToolFactory:
    
    def __init__(self, collection):
        self.collection = collection
        self.parent_store_manager = ParentStoreManager()

    @staticmethod
    def _sort_docs_by_source_priority(results: List[Document], preferred_layers: List[str] | None = None) -> List[Document]:
        layer_priority = {
            str(source_type).strip().lower(): index
            for index, source_type in enumerate(preferred_layers or _DEFAULT_LAYERED_SOURCE_TYPES)
        }

        def sort_key(doc: Document):
            metadata = doc.metadata or {}
            source_type = str(metadata.get("source_type", "")).strip().lower()
            priority = layer_priority.get(source_type)
            if priority is None:
                priority = len(layer_priority) + _SOURCE_TYPE_PRIORITY.get(source_type, 99)
            score = float(metadata.get("rerank_score") or metadata.get("fusion_score") or metadata.get("score") or 0.0)
            return (priority, -score)

        return sorted(results, key=sort_key)

    @staticmethod
    def _preferred_source_layers(query: str) -> List[str]:
        normalized = (query or "").strip().lower()
        matches = {source_type: 0 for source_type in _DEFAULT_LAYERED_SOURCE_TYPES}
        for source_type, keywords in _QUERY_TYPE_KEYWORDS.items():
            matches[source_type] = sum(1 for keyword in keywords if keyword in normalized)

        if matches["clinical_guideline"] > max(matches["patient_education"], matches["public_health"]):
            return ["clinical_guideline", "patient_education", "public_health"]
        if matches["public_health"] > max(matches["patient_education"], matches["clinical_guideline"]):
            return ["public_health", "patient_education", "clinical_guideline"]
        return list(_DEFAULT_LAYERED_SOURCE_TYPES)

    @classmethod
    def preferred_source_layers(cls, query: str) -> List[str]:
        return cls._preferred_source_layers(query)

    @staticmethod
    def _dedupe_docs(results: List[Document]) -> List[Document]:
        deduped = []
        seen = set()
        for doc in results:
            metadata = doc.metadata or {}
            key = (
                metadata.get("parent_id"),
                metadata.get("source"),
                doc.page_content.strip(),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(doc)
        return deduped

    @staticmethod
    def _doc_key(doc: Document):
        metadata = doc.metadata or {}
        return (
            metadata.get("parent_id"),
            metadata.get("source"),
            doc.page_content.strip(),
        )

    @staticmethod
    def _rrf_fuse(vector_results: List[Document], keyword_results: List[Document], limit: int) -> List[Document]:
        fused_scores = {}
        chosen_docs = {}
        for result_set in (vector_results, keyword_results):
            for rank, doc in enumerate(result_set, start=1):
                key = ToolFactory._doc_key(doc)
                fused_scores[key] = fused_scores.get(key, 0.0) + (1.0 / (_RRF_K + rank))
                chosen_docs.setdefault(key, doc)

        fused_docs = []
        for key, doc in chosen_docs.items():
            doc.metadata["fusion_score"] = round(fused_scores[key], 6)
            if not doc.metadata.get("score"):
                doc.metadata["score"] = doc.metadata["fusion_score"]
            fused_docs.append(doc)
        fused_docs.sort(key=lambda item: float((item.metadata or {}).get("fusion_score") or 0.0), reverse=True)
        return fused_docs[:limit]

    def _similarity_search_with_optional_filters(self, query: str, limit: int, score_threshold: float, source_types=None, rerank=True) -> List[Document]:
        try:
            return self.collection.similarity_search(
                query,
                k=limit,
                score_threshold=score_threshold,
                source_types=source_types,
                rerank=rerank,
            )
        except TypeError:
            results = self.collection.similarity_search(query, k=limit, score_threshold=score_threshold)
            if source_types:
                allowed = {str(item).strip().lower() for item in source_types}
                results = [
                    doc for doc in results
                    if str((doc.metadata or {}).get("source_type", "")).strip().lower() in allowed
                ]
            return results[:limit]

    def _keyword_search_with_optional_filters(self, query: str, limit: int, source_types=None) -> List[Document]:
        keyword_search = getattr(self.collection, "keyword_search", None)
        if not callable(keyword_search):
            return []
        try:
            return keyword_search(query, k=limit, source_types=source_types)
        except TypeError:
            results = keyword_search(query, k=limit)
            if source_types:
                allowed = {str(item).strip().lower() for item in source_types}
                results = [
                    doc for doc in results
                    if str((doc.metadata or {}).get("source_type", "")).strip().lower() in allowed
                ]
            return results[:limit]

    def _layered_similarity_search(self, query: str, limit: int, score_threshold: float) -> List[Document]:
        per_tier_limit = max(limit, 3)
        layered_results = []
        source_layers = self._preferred_source_layers(query)
        for source_type in source_layers:
            vector_results = self._similarity_search_with_optional_filters(
                query,
                limit=per_tier_limit,
                score_threshold=score_threshold,
                source_types=[source_type],
                rerank=False,
            )
            tier_results = vector_results
            if config.ENABLE_HYBRID_RETRIEVAL:
                keyword_results = self._keyword_search_with_optional_filters(
                    query,
                    limit=per_tier_limit,
                    source_types=[source_type],
                )
                tier_results = self._rrf_fuse(vector_results, keyword_results, per_tier_limit)
            layered_results.extend(tier_results)
            deduped = self._dedupe_docs(layered_results)
            if len(deduped) >= limit:
                layered_results = deduped
                break
            layered_results = deduped

        if len(layered_results) < limit:
            fallback_vector_results = self._similarity_search_with_optional_filters(
                query,
                limit=max(limit * 2, 6),
                score_threshold=score_threshold,
                source_types=None,
                rerank=False,
            )
            fallback_results = fallback_vector_results
            if config.ENABLE_HYBRID_RETRIEVAL:
                fallback_keyword_results = self._keyword_search_with_optional_filters(
                    query,
                    limit=max(limit * 2, 6),
                    source_types=None,
                )
                fallback_results = self._rrf_fuse(
                    fallback_vector_results,
                    fallback_keyword_results,
                    max(limit * 2, 6),
                )
            layered_results = self._dedupe_docs(layered_results + fallback_results)

        layered_results = self._sort_docs_by_source_priority(layered_results, preferred_layers=source_layers)
        rerank_candidates = getattr(self.collection, "rerank_candidates", None)
        if callable(rerank_candidates):
            layered_results = rerank_candidates(query, layered_results, limit)
            layered_results = self._sort_docs_by_source_priority(layered_results, preferred_layers=source_layers)
        return layered_results[:limit]

    def search_documents(self, query: str, limit: int = 4, score_threshold: float = 0.7) -> List[Document]:
        return self._layered_similarity_search(query, limit=limit, score_threshold=score_threshold)

    def _log_retrieval(self, query: str, limit: int, results: List[Document]):
        logger = getattr(self.collection, "log_retrieval", None)
        if not callable(logger):
            return
        context = get_retrieval_context()
        logger(
            thread_id=context.get("thread_id") or None,
            query_text=context.get("original_query") or query,
            rewritten_query=query,
            retrieval_mode="hybrid_layered" if config.ENABLE_HYBRID_RETRIEVAL else "vector_layered",
            top_k=limit,
            result_count=len(results),
            selected_parent_ids=[doc.metadata.get("parent_id") for doc in results if (doc.metadata or {}).get("parent_id")],
        )
    
    def _search_child_chunks(self, query: str, limit: int) -> str:
        """Search for the top K most relevant child chunks.
        
        Args:
            query: Search query string
            limit: Maximum number of results to return
        """
        try:
            results = self._layered_similarity_search(query, limit=limit, score_threshold=0.7)
            self._log_retrieval(query, limit, results)
            if not results:
                return _NO_EVIDENCE_RESPONSE

            confidence_bucket = _confidence_bucket(results)
            formatted_results = []
            for doc in results:
                metadata = doc.metadata or {}
                formatted_results.append(
                    f"Parent ID: {metadata.get('parent_id', '')}\n"
                    f"File Name: {metadata.get('source', '')}\n"
                    f"Source Title: {metadata.get('title', metadata.get('source', ''))}\n"
                    f"Source Type: {metadata.get('source_type', 'unknown')}\n"
                    f"Original URL: {metadata.get('original_url', '')}\n"
                    f"Published At: {metadata.get('published_at', '')}\n"
                    f"Freshness Bucket: {metadata.get('freshness_bucket', '')}\n"
                    f"Score: {float(metadata.get('rerank_score') or metadata.get('fusion_score') or metadata.get('score') or 0.0):.4f}\n"
                    f"Confidence Bucket: {confidence_bucket}\n"
                    f"Content: {doc.page_content.strip()}"
                )

            return "\n\n".join(formatted_results)

        except Exception as e:
            return f"RETRIEVAL_ERROR: {str(e)}"
    
    def _retrieve_many_parent_chunks(self, parent_ids: List[str]) -> str:
        """Retrieve full parent chunks by their IDs.
    
        Args:
            parent_ids: List of parent chunk IDs to retrieve
        """
        try:
            ids = [parent_ids] if isinstance(parent_ids, str) else list(parent_ids)
            raw_parents = self.parent_store_manager.load_content_many(ids)
            if not raw_parents:
                return "NO_PARENT_DOCUMENTS"

            return "\n\n".join([
                f"Parent ID: {doc.get('parent_id', 'n/a')}\n"
                f"File Name: {doc.get('metadata', {}).get('source', 'unknown')}\n"
                f"Source Title: {doc.get('metadata', {}).get('title', doc.get('metadata', {}).get('source', 'unknown'))}\n"
                f"Source Type: {doc.get('metadata', {}).get('source_type', 'unknown')}\n"
                f"Original URL: {doc.get('metadata', {}).get('original_url', '')}\n"
                f"Published At: {doc.get('metadata', {}).get('published_at', '')}\n"
                f"Freshness Bucket: {doc.get('metadata', {}).get('freshness_bucket', '')}\n"
                f"Content: {doc.get('content', '').strip()}"
                for doc in raw_parents
            ])            

        except Exception as e:
            return f"PARENT_RETRIEVAL_ERROR: {str(e)}"
    
    def _retrieve_parent_chunks(self, parent_id: str) -> str:
        """Retrieve full parent chunks by their IDs.
    
        Args:
            parent_id: Parent chunk ID to retrieve
        """
        try:
            parent = self.parent_store_manager.load_content(parent_id)
            if not parent:
                return "NO_PARENT_DOCUMENT"

            return (
                f"Parent ID: {parent.get('parent_id', 'n/a')}\n"
                f"File Name: {parent.get('metadata', {}).get('source', 'unknown')}\n"
                f"Source Title: {parent.get('metadata', {}).get('title', parent.get('metadata', {}).get('source', 'unknown'))}\n"
                f"Source Type: {parent.get('metadata', {}).get('source_type', 'unknown')}\n"
                f"Original URL: {parent.get('metadata', {}).get('original_url', '')}\n"
                f"Published At: {parent.get('metadata', {}).get('published_at', '')}\n"
                f"Freshness Bucket: {parent.get('metadata', {}).get('freshness_bucket', '')}\n"
                f"Content: {parent.get('content', '').strip()}"
            )          

        except Exception as e:
            return f"PARENT_RETRIEVAL_ERROR: {str(e)}"

    def create_tools(self) -> List:
        """Create and return the list of tools."""
        search_tool = tool("search_child_chunks")(self._search_child_chunks)
        retrieve_tool = tool("retrieve_parent_chunks")(self._retrieve_parent_chunks)
        
        return [search_tool, retrieve_tool]
