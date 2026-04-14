import os

# --- Directory Configuration ---
_BASE_DIR = os.path.dirname(os.path.dirname(__file__))

MARKDOWN_DIR = os.path.join(_BASE_DIR, "markdown_docs")
PARENT_STORE_PATH = os.path.join(_BASE_DIR, "parent_store")
QDRANT_DB_PATH = os.path.join(_BASE_DIR, "qdrant_db")

# --- Qdrant Configuration ---
CHILD_COLLECTION = "document_child_chunks"
SPARSE_VECTOR_NAME = "sparse"

# --- Model Configuration ---
DENSE_MODEL = "sentence-transformers/all-mpnet-base-v2"
SPARSE_MODEL = "Qdrant/bm25"

# --- LLM Provider Configuration ---
# 选择 LLM 提供商: "openai", "anthropic", "google", "ollama"
LLM_PROVIDER = "openai"

# 根据提供商设置对应模型和 API Key 环境变量
LLM_CONFIGS = {
    "openai": {
        "model": "gpt-4o-mini",  # 或 gpt-4o, gpt-3.5-turbo
        "api_key_env": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_API_BASE_URL",  # 可选，用于代理
    },
    "anthropic": {
        "model": "claude-3-5-sonnet-20241022",  # 或 claude-3-haiku-20240307
        "api_key_env": "ANTHROPIC_API_KEY",
    },
    "google": {
        "model": "gemini-2.0-flash",  # 或 gemini-1.5-pro
        "api_key_env": "GOOGLE_API_KEY",
    },
    "ollama": {
        "model": "qwen3:4b-instruct-2507-q4_K_M",
        "base_url": "http://localhost:11434",
    }
}

LLM_TEMPERATURE = 0

# --- Agent Configuration ---
MAX_TOOL_CALLS = 8
MAX_ITERATIONS = 10
GRAPH_RECURSION_LIMIT = 50
BASE_TOKEN_THRESHOLD = 2000
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
