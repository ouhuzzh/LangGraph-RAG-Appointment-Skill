import json
import config
import psycopg
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from model_factory import get_embedding_model


def _vector_literal(values):
    return "[" + ",".join(f"{float(v):.8f}" for v in values) + "]"


class PgVectorCollection:
    def __init__(self, conninfo: str, embeddings: Embeddings):
        self._conninfo = conninfo
        self._embeddings = embeddings

    def _connect(self):
        return psycopg.connect(self._conninfo)

    def _get_document_id(self, cur, metadata):
        source_name = metadata.get("source", "unknown.pdf")
        document_no = source_name.rsplit(".", 1)[0]
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
                    source_name,
                    source_name,
                    source_name.rsplit(".", 1)[-1].lower() if "." in source_name else "pdf",
                    json.dumps({"source": source_name}, ensure_ascii=False),
                ),
            )
            row = cur.fetchone()
        return row[0]

    def add_documents(self, documents):
        if not documents:
            return

        texts = [doc.page_content for doc in documents]
        embeddings = self._embeddings.embed_documents(texts)

        with self._connect() as conn:
            with conn.cursor() as cur:
                for index, (doc, embedding) in enumerate(zip(documents, embeddings)):
                    metadata = dict(doc.metadata)
                    chunk_id = metadata.get("chunk_id") or f"{metadata.get('parent_id', 'chunk')}_child_{index}"
                    document_id = self._get_document_id(cur, metadata)
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

    def similarity_search(self, query, k=4, score_threshold=None):
        query_embedding = self._embeddings.embed_query(query)
        fetch_limit = max(k * 3, k)

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        content,
                        metadata,
                        1 - (embedding <=> CAST(%s AS vector)) AS score
                    FROM child_chunks
                    ORDER BY embedding <=> CAST(%s AS vector)
                    LIMIT %s
                    """,
                    (_vector_literal(query_embedding), _vector_literal(query_embedding), fetch_limit),
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
            if len(results) >= k:
                break
        return results


class VectorDbManager:
    def __init__(self):
        self.__conninfo = (
            f"host={config.POSTGRES_HOST} "
            f"port={config.POSTGRES_PORT} "
            f"dbname={config.POSTGRES_DB} "
            f"user={config.POSTGRES_USER} "
            f"password={config.POSTGRES_PASSWORD}"
        )
        self.__dense_embeddings = get_embedding_model()

    def _connect(self):
        return psycopg.connect(self.__conninfo)

    def create_collection(self, collection_name):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            conn.commit()
        print(f"PostgreSQL vector store ready: {collection_name}")

    def delete_collection(self, collection_name):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE child_chunks RESTART IDENTITY CASCADE")
            conn.commit()

    def get_collection(self, collection_name):
        return PgVectorCollection(self.__conninfo, self.__dense_embeddings)
