from dataclasses import dataclass, field
from pathlib import Path
import re

from core.medical_source_ingest import html_to_markdown


SUPPORTED_UNSTRUCTURED_EXTENSIONS = {
    ".doc",
    ".docx",
    ".eml",
    ".epub",
    ".html",
    ".htm",
    ".odt",
    ".ppt",
    ".pptx",
    ".rtf",
    ".txt",
    ".xlsx",
    ".xls",
}


@dataclass
class DocumentConversionResult:
    output_path: Path
    method_used: str
    extracted_char_count: int
    warnings: list[str] = field(default_factory=list)


def supported_upload_extensions() -> set[str]:
    return {".pdf", ".md", *SUPPORTED_UNSTRUCTURED_EXTENSIONS}


def _clean_markdown_text(value: str) -> str:
    cleaned_lines = []
    blank_count = 0
    for raw_line in str(value or "").replace("\r\n", "\n").splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            blank_count += 1
            if blank_count <= 1:
                cleaned_lines.append("")
            continue
        blank_count = 0
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip() + "\n"


def _plain_text_to_markdown(path: Path) -> str:
    content = path.read_text(encoding="utf-8", errors="ignore").strip()
    if re.match(r"^\s*#", content):
        return content
    return f"# {path.stem}\n\n{content}".strip()


def _html_file_to_markdown(path: Path) -> str:
    content = path.read_text(encoding="utf-8", errors="ignore")
    markdown = html_to_markdown(content)
    if re.match(r"^\s*#", markdown):
        return markdown
    return f"# {path.stem}\n\n{markdown}".strip()


def _elements_to_markdown(elements) -> str:
    parts = []
    previous_title = False
    for element in elements or []:
        text = str(getattr(element, "text", "") or "").strip()
        if not text:
            continue
        category = str(getattr(element, "category", "") or element.__class__.__name__).lower()
        if "title" in category:
            prefix = "##" if previous_title else "#"
            parts.append(f"{prefix} {text}")
            previous_title = True
        elif "list" in category:
            parts.append(f"- {text}")
            previous_title = False
        elif "table" in category:
            metadata = getattr(element, "metadata", None)
            table_html = getattr(metadata, "text_as_html", "") if metadata else ""
            parts.append(table_html or text)
            previous_title = False
        else:
            parts.append(text)
            previous_title = False
    return "\n\n".join(parts)


def unstructured_to_markdown(document_path, output_dir) -> DocumentConversionResult:
    source_path = Path(document_path)
    suffix = source_path.suffix.lower()
    output_path = (Path(output_dir) / source_path.stem).with_suffix(".md")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    warnings = []
    markdown = ""
    method_used = "unstructured"

    try:
        from unstructured.partition.auto import partition

        elements = partition(filename=str(source_path))
        markdown = _elements_to_markdown(elements)
    except ImportError as exc:
        if suffix == ".txt":
            markdown = _plain_text_to_markdown(source_path)
            method_used = "plain_text_fallback"
            warnings.append("Optional dependency `unstructured` is not installed; used plain text fallback.")
        elif suffix in {".html", ".htm"}:
            markdown = _html_file_to_markdown(source_path)
            method_used = "html_fallback"
            warnings.append("Optional dependency `unstructured` is not installed; used HTML fallback.")
        else:
            raise RuntimeError(
                "Parsing this file type requires the optional dependency `unstructured`. "
                "Install it with: pip install \"unstructured[docx,pptx,xlsx,html]\""
            ) from exc

    markdown = _clean_markdown_text(markdown)
    if not markdown.strip():
        raise ValueError(f"No text could be extracted from {source_path.name}.")

    output_path.write_text(markdown, encoding="utf-8")
    return DocumentConversionResult(
        output_path=output_path,
        method_used=method_used,
        extracted_char_count=len(markdown.strip()),
        warnings=warnings,
    )
