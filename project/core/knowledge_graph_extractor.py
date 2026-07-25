"""Knowledge Graph Extractor — LLM-based medical entity/relation extraction.

Extracts (subject, subject_type, relation, object, object_type) triples from
parent chunk content at ingest time.  Stored in ``kg_triples`` for graph-hop
retrieval during the RAG pipeline.

Gated by ``config.ENABLE_GRAPH_RAG`` (off by default).  Fail-open: any LLM or
parse failure leaves the chunk without triples — ingest never breaks.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import List

import config

logger = logging.getLogger(__name__)


_EXTRACTION_PROMPT = (
    "你是医疗知识图谱构建助手。请从下面的医疗文本中抽取实体和关系三元组。\n"
    "实体类型限定为：疾病(disease)、症状(symptom)、科室(department)、"
    "药物(drug)、检查(examination)、治疗(treatment)。\n"
    "关系类型限定为：has_symptom、treats、belongs_to、requires_exam、"
    "contraindicated、causes、prevents、recommends。\n\n"
    "请以 JSON 数组输出，每个元素格式：\n"
    '{{"subject": "...", "subject_type": "...", "relation": "...", '
    '"object": "...", "object_type": "..."}}\n\n'
    "只输出 JSON 数组，不要解释。最多输出 {max_triples} 个三元组。\n\n"
    "文本：\n{text}"
)

VALID_ENTITY_TYPES = {"disease", "symptom", "department", "drug", "examination", "treatment"}
VALID_RELATIONS = {
    "has_symptom", "treats", "belongs_to", "requires_exam",
    "contraindicated", "causes", "prevents", "recommends",
}


@dataclass
class Triple:
    subject: str
    subject_type: str
    relation: str
    object: str
    object_type: str
    source_parent_id: str = ""
    source_document_no: str = ""


def parse_triples_json(raw: str, *, source_parent_id: str = "", source_document_no: str = "") -> List[Triple]:
    """Parse LLM JSON output into validated Triple objects.

    Lenient: skips malformed entries, normalizes types to lowercase, filters
    unknown types/relations.  Pure function for easy testing.
    """
    triples: List[Triple] = []
    # Try to find a JSON array in the raw text
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        return triples
    try:
        items = json.loads(match.group())
    except (json.JSONDecodeError, ValueError):
        return triples
    if not isinstance(items, list):
        return triples
    for item in items:
        if not isinstance(item, dict):
            continue
        subj = str(item.get("subject") or "").strip()
        subj_type = str(item.get("subject_type") or "").strip().lower()
        rel = str(item.get("relation") or "").strip().lower()
        obj = str(item.get("object") or "").strip()
        obj_type = str(item.get("object_type") or "").strip().lower()
        if not (subj and obj and rel):
            continue
        if subj_type not in VALID_ENTITY_TYPES or obj_type not in VALID_ENTITY_TYPES:
            continue
        if rel not in VALID_RELATIONS:
            continue
        triples.append(Triple(
            subject=subj,
            subject_type=subj_type,
            relation=rel,
            object=obj,
            object_type=obj_type,
            source_parent_id=source_parent_id,
            source_document_no=source_document_no,
        ))
    return triples


class KnowledgeGraphExtractor:
    """Extract medical knowledge triples from parent chunks via LLM.

    Lazy LLM initialization, fail-open, flag-gated.
    """

    def __init__(self, llm=None, *, chat_model_factory=None):
        self._llm = llm
        self._chat_model_factory = chat_model_factory
        self._llm_resolved = llm is not None

    @property
    def enabled(self) -> bool:
        return bool(getattr(config, "ENABLE_GRAPH_RAG", False))

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
            logger.warning("KnowledgeGraphExtractor: LLM init failed; extraction disabled", exc_info=True)
            self._llm = None
        return self._llm

    def extract_from_parent(self, parent_id: str, parent_content: str, *, document_no: str = "") -> List[Triple]:
        """Extract triples from a single parent chunk. Never raises."""
        if not self.enabled or not parent_content:
            return []
        llm = self._get_llm()
        if llm is None:
            return []
        max_triples = int(getattr(config, "GRAPH_RAG_MAX_TRIPLES_PER_CHUNK", 10))
        max_chars = int(getattr(config, "GRAPH_RAG_PARENT_CHARS", 3000))
        text = parent_content[:max_chars]
        prompt = _EXTRACTION_PROMPT.format(max_triples=max_triples, text=text)
        try:
            from langchain_core.messages import HumanMessage
            max_tokens = int(getattr(config, "GRAPH_RAG_EXTRACTION_MAX_TOKENS", 512))
            base = llm.with_config(temperature=0.0).bind(max_tokens=max_tokens)
            resp = base.invoke([HumanMessage(content=prompt)])
            raw = str(getattr(resp, "content", "") or "")
            return parse_triples_json(raw, source_parent_id=parent_id, source_document_no=document_no)
        except Exception:
            logger.debug("KnowledgeGraphExtractor: extraction failed for parent %s", parent_id, exc_info=True)
            return []

    def extract_from_parents(self, parent_pairs, *, document_no: str = "") -> List[Triple]:
        """Extract triples from all parent chunks. Never raises."""
        if not self.enabled:
            return []
        all_triples: List[Triple] = []
        for parent_id, parent_doc in (parent_pairs or []):
            content = getattr(parent_doc, "page_content", "") or str(parent_doc)
            triples = self.extract_from_parent(parent_id, content, document_no=document_no)
            all_triples.extend(triples)
        return all_triples
