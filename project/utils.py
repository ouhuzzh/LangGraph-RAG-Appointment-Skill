import glob
import io
import os
import shutil
import contextlib
from dataclasses import dataclass, field
from pathlib import Path

import config
import pymupdf
import pymupdf.layout
import pymupdf4llm
import tiktoken


def clear_directory_contents(directory: Path) -> None:
    """Delete everything under directory but not the directory itself (safe for Docker volume / bind mount roots)."""
    directory = Path(directory)
    if not directory.is_dir():
        return
    for child in directory.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


os.environ["TOKENIZERS_PARALLELISM"] = "false"


@dataclass
class PdfConversionResult:
    output_path: Path
    method_used: str
    extracted_char_count: int
    warnings: list[str] = field(default_factory=list)


def _sanitize_text(value: str) -> str:
    return (value or "").encode("utf-8", errors="surrogatepass").decode("utf-8", errors="ignore")


def _clean_markdown_text(value: str) -> str:
    cleaned_lines = []
    blank_count = 0
    for raw_line in _sanitize_text(value).replace("\r\n", "\n").splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            blank_count += 1
            if blank_count <= 1:
                cleaned_lines.append("")
            continue
        blank_count = 0
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip() + "\n"


def _extract_plain_text_markdown(doc) -> str:
    page_sections = []
    for page_index, page in enumerate(doc, start=1):
        page_text = _sanitize_text(page.get_text("text")).strip()
        if not page_text:
            continue
        page_sections.append(f"## Page {page_index}\n\n{page_text}")
    return _clean_markdown_text("\n\n".join(page_sections))


def _extract_ocr_markdown(doc) -> tuple[str, list[str]]:
    warnings = []
    languages = ("chi_sim+eng", "eng", "chi_sim")
    for language in languages:
        page_sections = []
        try:
            for page_index, page in enumerate(doc, start=1):
                if not hasattr(page, "get_textpage_ocr"):
                    raise RuntimeError("PyMuPDF OCR is unavailable in the current runtime.")
                text_page = page.get_textpage_ocr(language=language, dpi=200, full=True)
                page_text = _sanitize_text(page.get_text("text", textpage=text_page)).strip()
                if page_text:
                    page_sections.append(f"## Page {page_index}\n\n{page_text}")
        except Exception as exc:
            warnings.append(f"OCR attempt with '{language}' failed: {exc}")
            continue
        markdown = _clean_markdown_text("\n\n".join(page_sections))
        if markdown.strip():
            return markdown, warnings
        warnings.append(f"OCR attempt with '{language}' produced no text.")
    return "", warnings


def pdf_to_markdown(pdf_path, output_dir, *, min_chars=80):
    doc = pymupdf.open(pdf_path)
    warnings = []
    try:
        try:
            captured_stdout = io.StringIO()
            captured_stderr = io.StringIO()
            with contextlib.redirect_stdout(captured_stdout), contextlib.redirect_stderr(captured_stderr):
                md = pymupdf4llm.to_markdown(
                    doc,
                    header=False,
                    footer=False,
                    page_separators=True,
                    ignore_images=True,
                    write_images=False,
                    image_path=None,
                )
            library_messages = "\n".join(
                value.strip()
                for value in (captured_stdout.getvalue(), captured_stderr.getvalue())
                if value.strip()
            )
            if library_messages:
                warnings.append(f"Primary extractor note: {library_messages}")
            md_cleaned = _clean_markdown_text(md)
        except Exception as exc:
            warnings.append(f"Primary PDF layout extraction failed: {exc}")
            md_cleaned = ""
        method_used = "pymupdf4llm"
        if len(md_cleaned.strip()) < min_chars:
            warnings.append("Primary PDF layout extraction produced limited text; trying plain-text fallback.")
            plain_text_markdown = _extract_plain_text_markdown(doc)
            if len(plain_text_markdown.strip()) >= len(md_cleaned.strip()):
                md_cleaned = plain_text_markdown
                method_used = "plain_text_fallback"
            if len(md_cleaned.strip()) < min_chars:
                warnings.append("Plain-text fallback still produced limited text; trying OCR fallback.")
                ocr_markdown, ocr_warnings = _extract_ocr_markdown(doc)
                warnings.extend(ocr_warnings)
                if len(ocr_markdown.strip()) >= len(md_cleaned.strip()):
                    md_cleaned = ocr_markdown
                    method_used = "ocr_fallback"
        output_path = (Path(output_dir) / Path(doc.name).stem).with_suffix(".md")
        output_path.write_text(md_cleaned, encoding="utf-8")
        return PdfConversionResult(
            output_path=output_path,
            method_used=method_used,
            extracted_char_count=len(md_cleaned.strip()),
            warnings=warnings,
        )
    finally:
        close = getattr(doc, "close", None)
        if callable(close):
            close()

def pdfs_to_markdowns(path_pattern, overwrite: bool = False):
    output_dir = Path(config.MARKDOWN_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    for pdf_path in map(Path, glob.glob(path_pattern)):
        md_path = (output_dir / pdf_path.stem).with_suffix(".md")
        if overwrite or not md_path.exists():
            pdf_to_markdown(pdf_path, output_dir)

def estimate_context_tokens(messages: list) -> int:
    try:
        encoding = tiktoken.encoding_for_model("gpt-4")
    except:
        encoding = tiktoken.get_encoding("cl100k_base")
    return sum(len(encoding.encode(str(msg.content))) for msg in messages if hasattr(msg, 'content') and msg.content)
