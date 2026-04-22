import json
import config
import psycopg
import httpx
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from db.document_ids import build_document_no
from db.schema_manager import SchemaManager
from model_factory import get_embedding_model


def _vector_literal(values):
    return "[" + ",".join(f"{float(v):.8f}" for v in values) + "]"


def _build_embedding_text(doc):
    metadata = dict(doc.metadata or {})
    context_parts = []
    for key in ("section_title", "document_topic", "intended_audience", "source_version", "source_type", "title"):
        value = str(metadata.get(key) or "").strip()
        if value:
            context_parts.append(f"{key}: {value}")
    if context_parts:
        return "\n".join(context_parts) + "\n\n" + doc.page_content
    return doc.page_content


class PgVectorCollection:
    def __init__(self, conninfo: str, embeddings: Embeddings):
        self._conninfo = conninfo
        self._embeddings = embeddings
        self._rerank_client = None

    def _connect(self):
        return psycopg.connect(self._conninfo)

    def _get_rerank_client(self):
        if self._rerank_client is None:
            self._rerank_client = httpx.Client(timeout=30.0)
        return self._rerank_client

    def _rerank_documents(self, query, candidates, top_n):
        if not candidates or not config.ENABLE_RERANK or not config.RERANK_API_KEY or not config.RERANK_MODEL:
            return candidates[:top_n]

        documents = [doc.page_content for doc in candidates]
        payload = {
            "model": config.RERANK_MODEL,
            "query": query,
            "documents": documents,
            "top_n": min(top_n, len(documents)),
            "return_documents": False,
        }
        headers = {
            "Authorization": f"Bearer {config.RERANK_API_KEY}",
            "Content-Type": "application/json",
        }

        try:
            client = self._get_rerank_client()
            response = client.post(config.RERANK_BASE_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        except Exception:
            return candidates[:top_n]

        ranked_items = data.get("results") or data.get("data") or []
        reranked = []
        for item in ranked_items:
            index = item.get("index")
            if index is None or index >= len(candidates):
                continue
            doc = candidates[index]
            doc.metadata["rerank_score"] = item.get("relevance_score") or item.get("score")
            reranked.append(doc)

        return reranked or candidates[:top_n]

    def rerank_candidates(self, query, candidates, top_n):
        return self._rerank_documents(query, candidates, top_n)

    def log_retrieval(
        self,
        thread_id=None,
        query_text="",
        rewritten_query="",
        retrieval_mode="",
        top_k=None,
        result_count=0,
        selected_parent_ids=None,
        query_plan=None,
        graded_doc_count=0,
        sufficiency_result="",
        retry_count=0,
        final_confidence_bucket="",
    ):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO retrieval_logs (
                        thread_id, query_text, rewritten_query, retrieval_mode,
                        top_k, result_count, selected_parent_ids,
                        query_plan, graded_doc_count, sufficiency_result, retry_count, final_confidence_bucket
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)
                    """,
                    (
                        thread_id,
                        query_text,
                        rewritten_query or None,
                        retrieval_mode or None,
                        top_k,
                        result_count,
                        json.dumps(selected_parent_ids or [], ensure_ascii=False),
                        json.dumps(query_plan or [], ensure_ascii=False),
                        graded_doc_count,
                        sufficiency_result or None,
                        retry_count,
                        final_confidence_bucket or None,
                    ),
                )
            conn.commit()

    def _get_document_id(self, cur, metadata, cache=None):
        source_name = metadata.get("source", "unknown.pdf")
        document_no = build_document_no(source_name)
        if cache is not None and document_no in cache:
            return cache[document_no]
        cur.execute(
            """
            SELECT id FROM documents WHERE document_no = %s
            """,
            (document_no,),
        )
        row = cur.fetchone()
        if not row:
            cur.execute(
                """
                INSERT INTO documents (document_no, title, source_name, file_type, metadata)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (document_no)
                DO UPDATE SET updated_at = NOW()
                RETURNING id
                """,
                (
                    document_no,
                    metadata.get("title") or source_name,
                    source_name,
                    metadata.get("file_type") or (source_name.rsplit(".", 1)[-1].lower() if "." in source_name else "pdf"),
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
            row = cur.fetchone()
        if cache is not None:
            cache[document_no] = row[0]
        return row[0]

    def add_documents(self, documents):
        if not documents:
            return

        texts = [_build_embedding_text(doc) for doc in documents]
        embeddings = self._embeddings.embed_documents(texts)
        document_cache = {}

        with self._connect() as conn:
            with conn.cursor() as cur:
                for index, (doc, embedding) in enumerate(zip(documents, embeddings)):
                    metadata = dict(doc.metadata)
                    chunk_id = metadata.get("chunk_id") or f"{metadata.get('parent_id', 'chunk')}_child_{index}"
                    document_id = self._get_document_id(cur, metadata, cache=document_cache)
                    cur.execute(
                        """
                        INSERT INTO child_chunks (
                            chunk_id, parent_id, document_id, chunk_index, content,
                            token_count, department, metadata, embedding
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, CAST(%s AS vector))
                        ON CONFLICT (chunk_id)
                        DO UPDATE SET
                            parent_id = EXCLUDED.parent_id,
                            document_id = EXCLUDED.document_id,
                            chunk_index = EXCLUDED.chunk_index,
                            content = EXCLUDED.content,
                            token_count = EXCLUDED.token_count,
                            department = EXCLUDED.department,
                            metadata = EXCLUDED.metadata,
                            embedding = EXCLUDED.embedding
                        """,
                        (
                            chunk_id,
                            metadata.get("parent_id"),
                            document_id,
                            metadata.get("chunk_index", index),
                            doc.page_content,
                            len(doc.page_content),
                            metadata.get("department"),
                            json.dumps(metadata, ensure_ascii=False),
                            _vector_literal(embedding),
                        ),
                    )
            conn.commit()

    def similarity_search(self, query, k=4, score_threshold=None, source_types=None, rerank=True):
        query_embedding = self._embeddings.embed_query(query)
        fetch_limit = max(config.RERANK_FETCH_K, k)
        source_types = [str(item).strip().lower() for item in (source_types or []) if str(item).strip()]
        where_clauses = []
        params = []
        if source_types:
            where_clauses.append("lower(coalesce(metadata->>'source_type', '')) = ANY(%s)")
            params.append(source_types)
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        content,
                        metadata,
                        1 - (embedding <=> CAST(%s AS vector)) AS score
                    FROM child_chunks
                    {where_sql}
                    ORDER BY embedding <=> CAST(%s AS vector)
                    LIMIT %s
                    """,
                    [_vector_literal(query_embedding), *params, _vector_literal(query_embedding), fetch_limit],
                )
                rows = cur.fetchall()

        results = []
        for content, metadata, score in rows:
            score_value = float(score)
            if score_threshold is not None and score_value < score_threshold:
                continue
            meta = dict(metadata or {})
            meta["score"] = score_value
            results.append(Document(page_content=content, metadata=meta))

        if not rerank:
            return results[:k]

        reranked = self._rerank_documents(query, results, k)
        return reranked[:k]

    def keyword_search(self, query, k=4, source_types=None):
        fetch_limit = max(config.KEYWORD_FETCH_K, k)
        source_types = [str(item).strip().lower() for item in (source_types or []) if str(item).strip()]
        where_clauses = ["tsv @@ websearch_to_tsquery('simple', %s)"]
        params = [query]
        if source_types:
            where_clauses.append("lower(coalesce(metadata->>'source_type', '')) = ANY(%s)")
            params.append(source_types)
        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        with self._connect() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        f"""
                        SELECT
                            content,
                            metadata,
                            ts_rank_cd(tsv, websearch_to_tsquery('simple', %s)) AS keyword_score
                        FROM child_chunks
                        {where_sql}
                        ORDER BY keyword_score DESC, id
                        LIMIT %s
                        """,
                        [query, *params, fetch_limit],
                    )
                except psycopg.Error:
                    cur.execute(
                        f"""
                        SELECT
                            content,
                            metadata,
                            ts_rank_cd(tsv, plainto_tsquery('simple', %s)) AS keyword_score
                        FROM child_chunks
                        WHERE tsv @@ plainto_tsquery('simple', %s)
                        {"AND lower(coalesce(metadata->>'source_type', '')) = ANY(%s)" if source_types else ""}
                        ORDER BY keyword_score DESC, id
                        LIMIT %s
                        """,
                        [query, query, *([source_types] if source_types else []), fetch_limit],
                    )
                rows = cur.fetchall()

        results = []
        for content, metadata, keyword_score in rows:
            meta = dict(metadata or {})
            meta["keyword_score"] = float(keyword_score or 0.0)
            meta["score"] = max(float(meta.get("score") or 0.0), float(keyword_score or 0.0))
            results.append(Document(page_content=content, metadata=meta))
        return results[:k]


class VectorDbManager:
    def __init__(self):
        self._conninfo = (
            f"host={config.POSTGRES_HOST} "
            f"port={config.POSTGRES_PORT} "
            f"dbname={config.POSTGRES_DB} "
            f"user={config.POSTGRES_USER} "
            f"password={config.POSTGRES_PASSWORD}"
        )
        self._dense_embeddings = get_embedding_model()
        self._schema_manager = SchemaManager(self._conninfo)

    def _connect(self):
        return psycopg.connect(self._conninfo)

    @property
    def conninfo(self):
        return self._conninfo

    @property
    def schema_manager(self):
        return self._schema_manager

    def create_collection(self, collection_name):
        self._schema_manager.apply_migrations()
        print(f"PostgreSQL vector store ready: {collection_name}")

    def delete_collection(self, collection_name):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE child_chunks RESTART IDENTITY CASCADE")
            conn.commit()

    def has_documents(self) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT EXISTS (SELECT 1 FROM child_chunks LIMIT 1)")
                return bool(cur.fetchone()[0])

    def get_collection_stats(self):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM documents),
                        (SELECT COUNT(*) FROM parent_chunks),
                        (SELECT COUNT(*) FROM child_chunks)
                    """
                )
                row = cur.fetchone() or (0, 0, 0)
        return {
            "documents": int(row[0]),
            "parent_chunks": int(row[1]),
            "child_chunks": int(row[2]),
        }

    def get_indexed_document_nos(self):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT document_no FROM documents")
                return {row[0] for row in cur.fetchall()}

    def get_schema_status(self):
        return self._schema_manager.inspect_schema()

    def get_collection(self, collection_name):
        return PgVectorCollection(self._conninfo, self._dense_embeddings)
