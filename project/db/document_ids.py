import hashlib
from pathlib import Path


def build_document_no(source_name: str, max_length: int = 64) -> str:
    stem = Path(str(source_name or "unknown.pdf")).stem or "unknown"
    if len(stem) <= max_length:
        return stem
    digest = hashlib.sha1(stem.encode("utf-8")).hexdigest()[:10]
    prefix_length = max(1, max_length - len(digest) - 1)
    return f"{stem[:prefix_length]}-{digest}"
