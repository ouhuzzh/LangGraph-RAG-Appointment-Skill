import sys
import unittest

from langchain_core.documents import Document

sys.path.insert(0, r"D:\nageoffer\agentic-rag-for-dummies\project")

from rag_agent.tools import ToolFactory  # noqa: E402


class FakeCollection:
    def __init__(self, docs=None, docs_by_source=None):
        self.docs = docs or []
        self.docs_by_source = docs_by_source or {}
        self.calls = []

    def similarity_search(self, query, k=4, score_threshold=None, source_types=None, rerank=True):
        self.calls.append(
            {
                "query": query,
                "k": k,
                "score_threshold": score_threshold,
                "source_types": list(source_types or []),
                "rerank": rerank,
            }
        )
        if source_types:
            source_type = source_types[0]
            return list(self.docs_by_source.get(source_type, []))
        return list(self.docs)

    def rerank_candidates(self, query, candidates, top_n):
        return candidates[:top_n]


class RetrievalSourcePriorityTests(unittest.TestCase):
    def test_search_child_chunks_prefers_patient_facing_sources(self):
        docs = [
            Document(
                page_content="Clinical guideline content",
                metadata={"parent_id": "p3", "source": "guideline.pdf", "source_type": "clinical_guideline", "score": 0.99},
            ),
            Document(
                page_content="Public health content",
                metadata={"parent_id": "p2", "source": "who.pdf", "source_type": "public_health", "score": 0.95},
            ),
            Document(
                page_content="Patient education content",
                metadata={"parent_id": "p1", "source": "medlineplus.pdf", "source_type": "patient_education", "score": 0.90},
            ),
        ]
        tool_factory = ToolFactory(FakeCollection(docs))

        result = tool_factory._search_child_chunks("asthma", limit=3)

        first_index = result.find("medlineplus.pdf")
        second_index = result.find("who.pdf")
        third_index = result.find("guideline.pdf")
        self.assertNotEqual(first_index, -1)
        self.assertNotEqual(second_index, -1)
        self.assertNotEqual(third_index, -1)
        self.assertLess(first_index, second_index)
        self.assertLess(second_index, third_index)
        self.assertIn("Source Type: patient_education", result)

    def test_sort_docs_by_source_priority_uses_score_within_same_tier(self):
        docs = [
            Document(page_content="A", metadata={"source_type": "patient_education", "score": 0.81}),
            Document(page_content="B", metadata={"source_type": "patient_education", "score": 0.93}),
        ]

        sorted_docs = ToolFactory._sort_docs_by_source_priority(docs)

        self.assertEqual(sorted_docs[0].page_content, "B")
        self.assertEqual(sorted_docs[1].page_content, "A")

    def test_layered_similarity_search_queries_tiers_before_fallback(self):
        docs_by_source = {
            "patient_education": [
                Document(page_content="patient", metadata={"parent_id": "p1", "source": "medlineplus.pdf", "source_type": "patient_education", "score": 0.80}),
            ],
            "public_health": [
                Document(page_content="public", metadata={"parent_id": "p2", "source": "who.pdf", "source_type": "public_health", "score": 0.82}),
            ],
            "clinical_guideline": [
                Document(page_content="clinical", metadata={"parent_id": "p3", "source": "guideline.pdf", "source_type": "clinical_guideline", "score": 0.95}),
            ],
        }
        collection = FakeCollection(docs_by_source=docs_by_source)
        tool_factory = ToolFactory(collection)

        results = tool_factory._layered_similarity_search("hypertension", limit=3, score_threshold=0.7)

        self.assertEqual([doc.metadata["source_type"] for doc in results], ["patient_education", "public_health", "clinical_guideline"])
        self.assertEqual(
            [call["source_types"] for call in collection.calls[:3]],
            [["patient_education"], ["public_health"], ["clinical_guideline"]],
        )


if __name__ == "__main__":
    unittest.main()
