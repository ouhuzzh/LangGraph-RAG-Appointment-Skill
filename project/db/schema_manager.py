import config
import psycopg
import threading
from pathlib import Path


class SchemaManager:
    """Apply lightweight, repeatable PostgreSQL schema migrations."""

    _MIGRATIONS = [
        (
            "001_summary_dedup_and_indexes",
            "Clean duplicate summaries and create stable relational indexes.",
            [
                """
                DELETE FROM chat_session_summaries t
                USING (
                    SELECT ctid
                    FROM (
                        SELECT
                            ctid,
                            ROW_NUMBER() OVER (
                                PARTITION BY thread_id, summary_type
                                ORDER BY updated_at DESC, created_at DESC, id DESC
                            ) AS row_num
                        FROM chat_session_summaries
                    ) ranked
                    WHERE ranked.row_num > 1
                ) dupes
                WHERE t.ctid = dupes.ctid
                """,
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_session_summaries_thread_type
                ON chat_session_summaries(thread_id, summary_type)
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_patient_id
                ON chat_sessions(patient_id)
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_appointments_patient_status_date
                ON appointments(patient_id, status, appointment_date)
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_documents_source_name
                ON documents(source_name)
                """,
            ],
        ),
        (
            "002_child_chunks_vector_index",
            "Install a pgvector ANN index for child chunk recall.",
            [
                f"""
                CREATE INDEX IF NOT EXISTS idx_child_chunks_embedding_cosine
                ON child_chunks
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = {config.VECTOR_INDEX_LISTS})
                """,
                "ANALYZE child_chunks",
            ],
        ),
        (
            "003_import_task_logs",
            "Persist recent import task history for the UI.",
            [
                """
                CREATE TABLE IF NOT EXISTS import_task_logs (
                    id                  BIGSERIAL PRIMARY KEY,
                    source              VARCHAR(64) NOT NULL,
                    label               VARCHAR(128),
                    status              VARCHAR(64) NOT NULL DEFAULT 'completed',
                    downloaded          INTEGER NOT NULL DEFAULT 0,
                    written             INTEGER NOT NULL DEFAULT 0,
                    skipped             INTEGER NOT NULL DEFAULT 0,
                    failed              INTEGER NOT NULL DEFAULT 0,
                    index_added         INTEGER NOT NULL DEFAULT 0,
                    index_skipped       INTEGER NOT NULL DEFAULT 0,
                    duration_ms         DOUBLE PRECISION NOT NULL DEFAULT 0,
                    note                TEXT,
                    conversion_details  JSONB NOT NULL DEFAULT '[]'::jsonb,
                    failure_details     JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_import_task_logs_created_at
                ON import_task_logs(created_at DESC)
                """,
            ],
        ),
    ]

    def __init__(self, conninfo: str):
        self._conninfo = conninfo
        self._base_schema_path = Path(__file__).with_name("sql") / "init_schema.sql"
        self._lock = threading.Lock()
        self._applied = False

    def _connect(self):
        return psycopg.connect(self._conninfo)

    def apply_migrations(self):
        with self._lock:
            if self._applied:
                return
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
                    cur.execute(self._base_schema_path.read_text(encoding="utf-8"))
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS schema_migrations (
                            version         VARCHAR(64) PRIMARY KEY,
                            description     TEXT NOT NULL,
                            applied_at      TIMESTAMP NOT NULL DEFAULT NOW()
                        )
                        """,
                    )
                    for version, description, statements in self._MIGRATIONS:
                        cur.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (version,))
                        if cur.fetchone():
                            continue
                        for statement in statements:
                            cur.execute(statement)
                        cur.execute(
                            """
                            INSERT INTO schema_migrations (version, description)
                            VALUES (%s, %s)
                            ON CONFLICT (version) DO NOTHING
                            """,
                            (version, description),
                        )
                conn.commit()
            self._applied = True

    def inspect_schema(self):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT extname
                    FROM pg_extension
                    WHERE extname IN ('vector', 'pg_trgm')
                    ORDER BY extname
                    """
                )
                extensions = {row[0] for row in cur.fetchall()}

                cur.execute(
                    """
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND indexname IN (
                          'uq_chat_session_summaries_thread_type',
                          'idx_child_chunks_embedding_cosine',
                          'idx_appointments_patient_status_date',
                          'idx_chat_sessions_patient_id',
                          'idx_documents_source_name',
                          'idx_import_task_logs_created_at'
                      )
                    """
                )
                indexes = {row[0] for row in cur.fetchall()}

                cur.execute("SELECT version FROM schema_migrations ORDER BY version")
                versions = [row[0] for row in cur.fetchall()]

        return {
            "extensions": sorted(extensions),
            "indexes": sorted(indexes),
            "versions": versions,
        }
