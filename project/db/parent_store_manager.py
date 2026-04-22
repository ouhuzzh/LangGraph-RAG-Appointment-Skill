import json
import config
from pathlib import Path
from typing import List, Dict
import psycopg
from db.document_ids import build_document_no


class ParentStoreManager:
    def __init__(self):
        self._conninfo = (
            f"host={config.POSTGRES_HOST} "
            f"port={config.POSTGRES_PORT} "
            f"dbname={config.POSTGRES_DB} "
            f"user={config.POSTGRES_USER} "
            f"password={config.POSTGRES_PASSWORD}"
        )

    def _connect(self):
        return psycopg.connect(self._conninfo)

    @staticmethod
    def _document_info_from_metadata(metadata: Dict) -> Dict:
        source_name = metadata.get("source", "unknown.pdf")
        source_path = Path(source_name)
        document_no = build_document_no(source_name)
        return {
            "document_no": document_no,
            "title": metadata.get("title") or source_name,
            "source_name": source_name,
            "file_type": metadata.get("file_type") or source_path.suffix.lstrip(".") or "pdf",
        }

    def _ensure_document(self, conn, metadata: Dict) -> int:
        info = self._document_info_from_metadata(metadata)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents (document_no, title, source_name, file_type, metadata)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (document_no)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    source_name = EXCLUDED.source_name,
                    file_type = EXCLUDED.file_type,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING id
                """,
                (
                    info["document_no"],
                    info["title"],
                    info["source_name"],
                    info["file_type"],
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
            row = cur.fetchone()
        return row[0]

    def save(self, parent_id: str, content: str, metadata: Dict) -> None:
        with self._connect() as conn:
            document_id = self._ensure_document(conn, metadata)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO parent_chunks (parent_id, document_id, title, department, content, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (parent_id)
                    DO UPDATE SET
                        document_id = EXCLUDED.document_id,
                        title = EXCLUDED.title,
                        department = EXCLUDED.department,
                        content = EXCLUDED.content,
                        metadata = EXCLUDED.metadata
                    """,
                    (
                        parent_id,
                        document_id,
                        metadata.get("H1") or metadata.get("H2") or metadata.get("H3") or metadata.get("source"),
                        metadata.get("department"),
                        content,
                        json.dumps(metadata, ensure_ascii=False),
                    ),
                )
            conn.commit()

    def save_many(self, parents: List) -> None:
        if not parents:
            return
        with self._connect() as conn:
            document_cache = {}
            with conn.cursor() as cur:
                for parent_id, doc in parents:
                    document_no = self._document_info_from_metadata(doc.metadata)["document_no"]
                    document_id = document_cache.get(document_no)
                    if document_id is None:
                        document_id = self._ensure_document(conn, doc.metadata)
                        document_cache[document_no] = document_id
                    cur.execute(
                        """
                        INSERT INTO parent_chunks (parent_id, document_id, title, department, content, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                        ON CONFLICT (parent_id)
                        DO UPDATE SET
                            document_id = EXCLUDED.document_id,
                            title = EXCLUDED.title,
                            department = EXCLUDED.department,
                            content = EXCLUDED.content,
                            metadata = EXCLUDED.metadata
                        """,
                        (
                            parent_id,
                            document_id,
                            doc.metadata.get("H1") or doc.metadata.get("H2") or doc.metadata.get("H3") or doc.metadata.get("source"),
                            doc.metadata.get("department"),
                            doc.page_content,
                            json.dumps(doc.metadata, ensure_ascii=False),
                        ),
                    )
            conn.commit()

    def load(self, parent_id: str) -> Dict:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT content, metadata
                    FROM parent_chunks
                    WHERE parent_id = %s
                    """,
                    (parent_id,),
                )
                row = cur.fetchone()
        if not row:
            raise FileNotFoundError(f"Parent chunk not found: {parent_id}")
        return {"page_content": row[0], "metadata": row[1] or {}}

    def load_content(self, parent_id: str) -> Dict:
        data = self.load(parent_id)
        return {
            "content": data["page_content"],
            "parent_id": parent_id,
            "metadata": data["metadata"],
        }

    def load_content_many(self, parent_ids: List[str]) -> List[Dict]:
        unique_ids = list(dict.fromkeys(parent_ids))
        if not unique_ids:
            return []

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT parent_id, content, metadata
                    FROM parent_chunks
                    WHERE parent_id = ANY(%s)
                    """,
                    (unique_ids,),
                )
                rows = cur.fetchall()

        row_map = {
            row[0]: {
                "content": row[1],
                "parent_id": row[0],
                "metadata": row[2] or {},
            }
            for row in rows
        }
        return [row_map[parent_id] for parent_id in unique_ids if parent_id in row_map]

    def clear_store(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE parent_chunks, documents RESTART IDENTITY CASCADE")
            conn.commit()
