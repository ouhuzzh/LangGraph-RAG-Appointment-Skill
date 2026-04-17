import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# --- Directory Configuration ---
_BASE_DIR = os.path.dirname(os.path.dirname(__file__))

MARKDOWN_DIR = os.path.join(_BASE_DIR, "markdown_docs")
PARENT_STORE_PATH = os.path.join(_BASE_DIR, "parent_store")
QDRANT_DB_PATH = os.path.join(_BASE_DIR, "qdrant_db")
VECTOR_DIMENSION = int(os.environ.get("VECTOR_DIMENSION", "1024"))

# --- Qdrant Configuration ---
CHILD_COLLECTION = "document_child_chunks"
SPARSE_VECTOR_NAME = "sparse"

# --- Multi-Provider Model Configuration ---
ACTIVE_LLM_PROVIDER = os.environ.get("ACTIVE_LLM_PROVIDER", "deepseek").lower()
ACTIVE_EMBEDDING_PROVIDER = os.environ.get("ACTIVE_EMBEDDING_PROVIDER", "openai_compatible").lower()

LLM_MODEL = os.environ.get("LLM_MODEL", "Qwen/Qwen3-32B")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")
RERANK_MODEL = os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0"))
ENABLE_RERANK = os.environ.get("ENABLE_RERANK", "true").lower() == "true"
RERANK_FETCH_K = int(os.environ.get("RERANK_FETCH_K", "12"))

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "")
OPENAI_ENABLE_THINKING = os.environ.get("OPENAI_ENABLE_THINKING", "false").lower() == "true"
OPENAI_THINKING_BUDGET = int(os.environ.get("OPENAI_THINKING_BUDGET", "1024"))
RERANK_API_KEY = os.environ.get("RERANK_API_KEY", OPENAI_API_KEY)
RERANK_BASE_URL = os.environ.get("RERANK_BASE_URL", "https://api.siliconflow.cn/v1/rerank")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

# Backward-compatible aliases used by the current vector layer.
DENSE_MODEL = EMBEDDING_MODEL
SPARSE_MODEL = os.environ.get("SPARSE_MODEL", "Qdrant/bm25")

# --- PostgreSQL Configuration ---
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.environ.get("POSTGRES_DB", "ai_companion")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")

# --- Redis Configuration ---
REDIS_ENABLED = os.environ.get("REDIS_ENABLED", "true").lower() == "true"
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_DB = int(os.environ.get("REDIS_DB", "0"))
REDIS_TTL_SECONDS = int(os.environ.get("REDIS_TTL_SECONDS", "86400"))
SHORT_TERM_WINDOW_SIZE = int(os.environ.get("SHORT_TERM_WINDOW_SIZE", "8"))
SUMMARY_REFRESH_THRESHOLD = int(os.environ.get("SUMMARY_REFRESH_THRESHOLD", "6"))
HIGH_RISK_KEYWORDS = [
    "胸痛",
    "胸闷",
    "呼吸困难",
    "呼吸急促",
    "意识模糊",
    "抽搐",
    "大出血",
    "持续高热",
    "晕厥",
    "severe chest pain",
    "shortness of breath",
    "confusion",
    "convulsion",
    "heavy bleeding",
]

# --- Agent Configuration ---
MAX_TOOL_CALLS = 8
MAX_ITERATIONS = 10
GRAPH_RECURSION_LIMIT = 50
BASE_TOKEN_THRESHOLD = 4000
TOKEN_GROWTH_FACTOR = 0.9

# --- Text Splitter Configuration ---
CHILD_CHUNK_SIZE = 500
CHILD_CHUNK_OVERLAP = 100
MIN_PARENT_SIZE = 2000
MAX_PARENT_SIZE = 4000
HEADERS_TO_SPLIT_ON = [
    ("#", "H1"),
    ("##", "H2"),
    ("###", "H3")
]

# --- Langfuse Observability ---
LANGFUSE_ENABLED = os.environ.get("LANGFUSE_ENABLED", "false").lower() == "true"
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")
LANGFUSE_BASE_URL = os.environ.get("LANGFUSE_BASE_URL", "http://localhost:3000")
