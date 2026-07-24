"""Contextual Retrieval — situate each child chunk before embedding.

Anthropic's Contextual Retrieval technique: before embedding a chunk, prepend a
short, LLM-generated sentence that explains the chunk's role within its parent
document.  This gives the embedding model disambiguating context that a
stand-alone chunk lacks, improving recall on the hybrid + rerank pipeline.

The enricher is gated by ``config.ENABLE_CONTEXTUAL_RETRIEVAL`` (off by default).
It is deliberately fail-open: any LLM/parse error leaves the chunk untouched so
ingestion never breaks.  The generated sentence is stored on
``chunk.metadata["contextual_summary"]`` and consumed by
``db.vector_db_manager._build_embedding_text``.
"""

from __future__ import annotations

import logging

import config

logger = logging.getLogger(__name__)


_CONTEXT_PROMPT = (
    "你是医疗知识库的检索优化助手。下面给出一篇文档的标题、所在章节，"
    "以及该章节中的一个文本块。请用一句不超过 {max_chars} 字的中文，"
    "概括这个文本块在整篇文档中的定位与主题，使它被单独检索时也能被准确理解。"
    "只输出这一句话，不要加引号、不要解释。\n\n"
    "文档标题：{title}\n所在章节：{section}\n"
    "章节上下文（节选）：\n{parent}\n\n"
    "文本块：\n{chunk}"
)


class ContextualChunkEnricher:
    """Attach an LLM-generated situating sentence to each child chunk.

    The LLM is resolved lazily on first use so constructing an enricher is cheap
    and free of import-time side effects (safe to inject at service bootstrap
    before the model runtime exists).
    """

    def __init__(self, llm=None, *, chat_model_factory=None):
        self._llm = llm
        self._chat_model_factory = chat_model_factory
        self._llm_resolved = llm is not None

    @property
    def enabled(self) -> bool:
        return bool(getattr(config, "ENABLE_CONTEXTUAL_RETRIEVAL", False))

    def _get_llm(self):
        if self._llm_resolved:
            return self._llm
        self._llm_resolved = True
        try:
            factory = self._chat_model_factory
            if factory is None:
                from model_factory import get_chat_model
                factory = get_chat_model
            self._llm = factory()
        except Exception:
            logger.warning(
                "ContextualChunkEnricher: LLM init failed; enrichment disabled",
                exc_info=True,
            )
            self._llm = None
        return self._llm

    def enrich_child_chunks(self, child_chunks, *, parent_lookup=None):
        """Set ``metadata['contextual_summary']`` on each child chunk in place.

        Returns the same list for convenience.  No-op when disabled, when the
        LLM is unavailable, or when ``child_chunks`` is empty.  Never raises.
        """
        if not self.enabled or not child_chunks:
            return child_chunks
        llm = self._get_llm()
        if llm is None:
            return child_chunks

        parent_lookup = parent_lookup or {}
        max_tokens = int(getattr(config, "CONTEXTUAL_RETRIEVAL_MAX_TOKENS", 128))
        try:
            base = llm.with_config(temperature=0.0).bind(max_tokens=max_tokens)
        except Exception:
            base = llm

        for doc in child_chunks:
            self._enrich_one(base, doc, parent_lookup)
        return child_chunks

    def _enrich_one(self, base, doc, parent_lookup):
        try:
            metadata = doc.metadata or {}
            if str(metadata.get("contextual_summary") or "").strip():
                return
            max_chars = int(getattr(config, "CONTEXTUAL_RETRIEVAL_MAX_CHARS", 80))
            chunk_chars = int(getattr(config, "CONTEXTUAL_RETRIEVAL_CHUNK_CHARS", 1200))
            parent_chars = int(getattr(config, "CONTEXTUAL_RETRIEVAL_PARENT_CHARS", 2000))
            title = str(
                metadata.get("document_topic")
                or metadata.get("title")
                or metadata.get("source")
                or "（未知）"
            ).strip()
            section = str(metadata.get("section_title") or "（未知）").strip()
            parent_text = str(parent_lookup.get(metadata.get("parent_id"), "") or "")[:parent_chars]
            prompt = _CONTEXT_PROMPT.format(
                max_chars=max_chars,
                title=title,
                section=section,
                parent=parent_text or "（无）",
                chunk=(doc.page_content or "")[:chunk_chars],
            )
            from langchain_core.messages import HumanMessage
            resp = base.invoke([HumanMessage(content=prompt)])
            summary = " ".join(str(getattr(resp, "content", "") or "").split()).strip()
            if summary:
                metadata["contextual_summary"] = summary[: max_chars * 2]
                doc.metadata = metadata
        except Exception:
            logger.debug("ContextualChunkEnricher: enrich failed for one chunk", exc_info=True)
