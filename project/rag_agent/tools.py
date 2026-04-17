from typing import List
from langchain_core.tools import tool
from langchain_core.documents import Document
from db.parent_store_manager import ParentStoreManager


_SOURCE_TYPE_PRIORITY = {
    "patient_education": 0,
    "public_health": 1,
    "clinical_guideline": 2,
    "research_article": 3,
}
_LAYERED_SOURCE_TYPES = ["patient_education", "public_health", "clinical_guideline"]


class ToolFactory:
    
    def __init__(self, collection):
        self.collection = collection
        self.parent_store_manager = ParentStoreManager()

    @staticmethod
    def _sort_docs_by_source_priority(results: List[Document]) -> List[Document]:
        def sort_key(doc: Document):
            metadata = doc.metadata or {}
            source_type = str(metadata.get("source_type", "")).strip().lower()
            priority = _SOURCE_TYPE_PRIORITY.get(source_type, 99)
            score = float(metadata.get("score") or metadata.get("rerank_score") or 0.0)
            return (priority, -score)

        return sorted(results, key=sort_key)

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

    def _layered_similarity_search(self, query: str, limit: int, score_threshold: float) -> List[Document]:
        per_tier_limit = max(limit, 3)
        layered_results = []
        for source_type in _LAYERED_SOURCE_TYPES:
            tier_results = self._similarity_search_with_optional_filters(
                query,
                limit=per_tier_limit,
                score_threshold=score_threshold,
                source_types=[source_type],
                rerank=False,
            )
            layered_results.extend(tier_results)
            deduped = self._dedupe_docs(layered_results)
            if len(deduped) >= limit:
                layered_results = deduped
                break
            layered_results = deduped

        if len(layered_results) < limit:
            fallback_results = self._similarity_search_with_optional_filters(
                query,
                limit=max(limit * 2, 6),
                score_threshold=score_threshold,
                source_types=None,
                rerank=False,
            )
            layered_results = self._dedupe_docs(layered_results + fallback_results)

        layered_results = self._sort_docs_by_source_priority(layered_results)
        rerank_candidates = getattr(self.collection, "rerank_candidates", None)
        if callable(rerank_candidates):
            layered_results = rerank_candidates(query, layered_results, limit)
            layered_results = self._sort_docs_by_source_priority(layered_results)
        return layered_results[:limit]
    
    def _search_child_chunks(self, query: str, limit: int) -> str:
        """Search for the top K most relevant child chunks.
        
        Args:
            query: Search query string
            limit: Maximum number of results to return
        """
        try:
            results = self._layered_similarity_search(query, limit=limit, score_threshold=0.7)
            if not results:
                return "NO_RELEVANT_CHUNKS"

            return "\n\n".join([
                f"Parent ID: {doc.metadata.get('parent_id', '')}\n"
                f"File Name: {doc.metadata.get('source', '')}\n"
                f"Source Type: {doc.metadata.get('source_type', 'unknown')}\n"
                f"Content: {doc.page_content.strip()}"
                for doc in results
            ])            

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
                f"Source Type: {doc.get('metadata', {}).get('source_type', 'unknown')}\n"
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
                f"Source Type: {parent.get('metadata', {}).get('source_type', 'unknown')}\n"
                f"Content: {parent.get('content', '').strip()}"
            )          

        except Exception as e:
            return f"PARENT_RETRIEVAL_ERROR: {str(e)}"
    
    def create_tools(self) -> List:
        """Create and return the list of tools."""
        search_tool = tool("search_child_chunks")(self._search_child_chunks)
        retrieve_tool = tool("retrieve_parent_chunks")(self._retrieve_parent_chunks)
        
        return [search_tool, retrieve_tool]
