import io
import json
import re
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import requests
from utils import pdf_to_markdown


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", (value or "").strip().lower())
    slug = slug.strip("-")
    return slug or "document"


def _collapse_text(value: str) -> str:
    lines = [line.strip() for line in (value or "").splitlines()]
    filtered = [line for line in lines if line]
    return "\n\n".join(filtered)


def _extract_first_match(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
    return ""


class _SimpleHtmlToMarkdownParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self._list_stack = []

    def handle_starttag(self, tag, attrs):
        if tag in {"p", "div", "section", "article", "br"}:
            self.parts.append("\n\n")
        elif tag in {"ul", "ol"}:
            self.parts.append("\n")
            self._list_stack.append(tag)
        elif tag == "li":
            self.parts.append("\n- ")

    def handle_endtag(self, tag):
        if tag in {"p", "div", "section", "article"}:
            self.parts.append("\n\n")
        elif tag in {"ul", "ol"} and self._list_stack:
            self._list_stack.pop()
            self.parts.append("\n")

    def handle_data(self, data):
        if data and data.strip():
            self.parts.append(data.strip())

    def get_markdown(self) -> str:
        return _collapse_text("".join(self.parts))


def html_to_markdown(value: str) -> str:
    parser = _SimpleHtmlToMarkdownParser()
    parser.feed(value or "")
    return parser.get_markdown()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_child_text(element: ET.Element, name: str) -> str:
    for child in list(element):
        if _local_name(child.tag) == name:
            return "".join(child.itertext()).strip()
    return ""


def _find_child_inner_xml(element: ET.Element, name: str) -> str:
    for child in list(element):
        if _local_name(child.tag) != name:
            continue
        parts = []
        if child.text:
            parts.append(child.text)
        for sub in list(child):
            parts.append(ET.tostring(sub, encoding="unicode", method="html"))
        return "".join(parts).strip()
    return ""


@dataclass
class ImportedMedicalDocument:
    source_id: str
    title: str
    source_url: str
    summary: str
    categories: list[str]
    related_terms: list[str]
    body_markdown: str


@dataclass
class MedicalImportResult:
    downloaded: int
    written: int
    skipped: int
    output_dir: Path
    discovered_url: str
    failed: int = 0
    failure_details: list[str] = field(default_factory=list)
    conversion_details: list[str] = field(default_factory=list)


class MedlinePlusXmlImporter:
    index_url = "https://medlineplus.gov/xml.html"

    def __init__(self, session=None):
        self.session = session or requests.Session()

    def discover_download_url(self, index_html: str) -> str:
        patterns = [
            r'href=["\'](?P<url>https://medlineplus\.gov/xml/[^"\']+\.zip)["\']',
            r'href=["\'](?P<url>/xml/[^"\']+\.zip)["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, index_html, re.IGNORECASE)
            if match:
                return urljoin(self.index_url, match.group("url"))
        raise ValueError("Could not locate a MedlinePlus XML archive link.")

    def fetch_latest_archive(self) -> tuple[str, bytes]:
        index_response = self.session.get(self.index_url, timeout=30)
        index_response.raise_for_status()
        archive_url = self.discover_download_url(index_response.text)

        archive_response = self.session.get(archive_url, timeout=60)
        archive_response.raise_for_status()
        return archive_url, archive_response.content

    def extract_xml_text(self, archive_bytes: bytes) -> str:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            xml_names = [name for name in archive.namelist() if name.lower().endswith(".xml")]
            if not xml_names:
                raise ValueError("No XML file found in MedlinePlus archive.")
            with archive.open(xml_names[0]) as handle:
                return handle.read().decode("utf-8")

    def parse_topics(self, xml_text: str, limit: int | None = None) -> list[ImportedMedicalDocument]:
        root = ET.fromstring(xml_text)
        topics = []
        for topic_element in root.iter():
            if _local_name(topic_element.tag) != "health-topic":
                continue

            title = topic_element.attrib.get("title") or _find_child_text(topic_element, "title")
            source_url = topic_element.attrib.get("url") or _find_child_text(topic_element, "url")
            summary = topic_element.attrib.get("meta-desc") or _find_child_text(topic_element, "meta-desc")
            body_html = _find_child_inner_xml(topic_element, "full-summary")
            categories = [
                "".join(child.itertext()).strip()
                for child in list(topic_element)
                if _local_name(child.tag) in {"group", "group-name"} and "".join(child.itertext()).strip()
            ]
            related_terms = [
                "".join(child.itertext()).strip()
                for child in list(topic_element)
                if _local_name(child.tag) in {"also-called", "see-reference"} and "".join(child.itertext()).strip()
            ]
            body_markdown = html_to_markdown(body_html)
            if not title or not body_markdown:
                continue

            topics.append(
                ImportedMedicalDocument(
                    source_id=f"medlineplus-{_slugify(title)}",
                    title=title,
                    source_url=source_url,
                    summary=summary,
                    categories=categories,
                    related_terms=related_terms,
                    body_markdown=body_markdown,
                )
            )
            if limit is not None and len(topics) >= limit:
                break
        return topics

    def render_topic_markdown(self, topic: ImportedMedicalDocument) -> str:
        metadata_lines = [
            f"Source: MedlinePlus",
            "Source type: patient_education",
            "Language: en",
            "File type: md",
            f"Title: {topic.title}",
            f"Original URL: {topic.source_url}",
        ]
        if topic.summary:
            metadata_lines.append(f"Summary: {topic.summary}")
        if topic.categories:
            metadata_lines.append(f"Categories: {', '.join(topic.categories)}")
        if topic.related_terms:
            metadata_lines.append(f"Related terms: {', '.join(topic.related_terms)}")

        sections = [
            f"# {topic.title}",
            "\n".join(metadata_lines),
            "## Content",
            topic.body_markdown,
        ]
        return "\n\n".join(section for section in sections if section.strip()) + "\n"

    def write_topics(self, topics: list[ImportedMedicalDocument], output_dir: str | Path, overwrite: bool = False) -> tuple[int, int]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        written = 0
        skipped = 0
        for topic in topics:
            file_path = output_path / f"{topic.source_id}.md"
            if file_path.exists() and not overwrite:
                skipped += 1
                continue
            file_path.write_text(self.render_topic_markdown(topic), encoding="utf-8")
            written += 1
        return written, skipped

    def import_latest(self, output_dir: str | Path, limit: int | None = None, overwrite: bool = False) -> MedicalImportResult:
        archive_url, archive_bytes = self.fetch_latest_archive()
        xml_text = self.extract_xml_text(archive_bytes)
        topics = self.parse_topics(xml_text, limit=limit)
        written, skipped = self.write_topics(topics, output_dir, overwrite=overwrite)
        return MedicalImportResult(
            downloaded=len(topics),
            written=written,
            skipped=skipped,
            output_dir=Path(output_dir),
            discovered_url=archive_url,
        )


class NhcPdfWhitelistImporter:
    def __init__(self, session=None, manifest_path: str | Path | None = None):
        self.session = session or requests.Session()
        self.manifest_path = Path(manifest_path) if manifest_path else Path(__file__).with_name("manifests") / "nhc_whitelist.json"

    def load_manifest(self) -> list[dict]:
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("NHC whitelist manifest must be a list.")
        return data

    def _download_pdf_bytes(self, entry: dict) -> bytes:
        pdf_url = entry["pdf_url"]
        response = self.session.get(pdf_url, timeout=90)
        response.raise_for_status()
        return response.content

    def _convert_pdf_bytes_to_markdown(self, pdf_bytes: bytes, stem: str) -> tuple[str, object]:
        with tempfile.TemporaryDirectory(prefix="nhc-pdf-") as temp_dir:
            temp_dir_path = Path(temp_dir)
            pdf_path = temp_dir_path / f"{stem}.pdf"
            pdf_path.write_bytes(pdf_bytes)
            conversion_result = pdf_to_markdown(str(pdf_path), temp_dir_path)
            markdown_path = temp_dir_path / f"{stem}.md"
            if not markdown_path.exists():
                raise FileNotFoundError(f"Markdown conversion failed for {stem}")
            return markdown_path.read_text(encoding="utf-8"), conversion_result

    def _render_entry_markdown(self, entry: dict, body_markdown: str) -> str:
        metadata_lines = [
            "Source: 国家卫生健康委员会",
            f"Source type: {entry.get('document_type', 'clinical_guideline')}",
            "Language: zh",
            "File type: pdf",
            f"Title: {entry['title']}",
            f"Original URL: {entry.get('page_url', entry['pdf_url'])}",
            f"PDF URL: {entry['pdf_url']}",
        ]
        if entry.get("document_type"):
            metadata_lines.append(f"Document type: {entry['document_type']}")
        if entry.get("department"):
            metadata_lines.append(f"Department: {entry['department']}")
        if entry.get("tags"):
            metadata_lines.append(f"Tags: {', '.join(entry['tags'])}")

        sections = [
            f"# {entry['title']}",
            "\n".join(metadata_lines),
            "## Content",
            _collapse_text(body_markdown),
        ]
        return "\n\n".join(section for section in sections if section.strip()) + "\n"

    def import_whitelist(self, output_dir: str | Path, limit: int | None = None, overwrite: bool = False) -> MedicalImportResult:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        entries = self.load_manifest()
        if limit is not None:
            entries = entries[:limit]

        written = 0
        skipped = 0
        failed = 0
        failure_details = []
        conversion_details = []
        for entry in entries:
            stem = entry.get("id") or f"nhc-{_slugify(entry['title'])}"
            markdown_path = output_path / f"{stem}.md"
            if markdown_path.exists() and not overwrite:
                skipped += 1
                continue
            try:
                pdf_bytes = self._download_pdf_bytes(entry)
                body_markdown, conversion_result = self._convert_pdf_bytes_to_markdown(pdf_bytes, stem)
                detail = (
                    f"{entry.get('title', stem)} | method={conversion_result.method_used} "
                    f"chars={conversion_result.extracted_char_count}"
                )
                if conversion_result.warnings:
                    detail += f" | warnings={' ; '.join(conversion_result.warnings[:2])}"
                conversion_details.append(detail)
                markdown_path.write_text(self._render_entry_markdown(entry, body_markdown), encoding="utf-8")
                written += 1
            except Exception as exc:
                print(f"Failed to import NHC document '{entry.get('title', stem)}': {exc}")
                failed += 1
                failure_details.append(f"{entry.get('title', stem)}: {exc}")

        return MedicalImportResult(
            downloaded=len(entries),
            written=written,
            skipped=skipped,
            output_dir=output_path,
            discovered_url=str(self.manifest_path),
            failed=failed,
            failure_details=failure_details,
            conversion_details=conversion_details,
        )


class WhoHtmlWhitelistImporter:
    def __init__(self, session=None, manifest_path: str | Path | None = None):
        self.session = session or requests.Session()
        self.manifest_path = Path(manifest_path) if manifest_path else Path(__file__).with_name("manifests") / "who_whitelist.json"

    def load_manifest(self) -> list[dict]:
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("WHO whitelist manifest must be a list.")
        return data

    def _download_html(self, entry: dict) -> str:
        url = entry["url"]
        response = self.session.get(url, timeout=60)
        response.raise_for_status()
        return response.text

    def _extract_article_html(self, html_text: str) -> str:
        article_html = _extract_first_match(
            html_text,
            [
                r"<article[^>]*>(.*?)</article>",
                r"<main[^>]*>(.*?)</main>",
            ],
        )
        if not article_html:
            raise ValueError("Could not locate WHO article content.")
        return article_html

    def _render_entry_markdown(self, entry: dict, body_markdown: str) -> str:
        metadata_lines = [
            "Source: World Health Organization",
            f"Source type: {entry.get('document_type', 'public_health')}",
            "Language: en",
            "File type: html",
            f"Title: {entry['title']}",
            f"Original URL: {entry['url']}",
        ]
        if entry.get("document_type"):
            metadata_lines.append(f"Document type: {entry['document_type']}")
        if entry.get("tags"):
            metadata_lines.append(f"Tags: {', '.join(entry['tags'])}")

        sections = [
            f"# {entry['title']}",
            "\n".join(metadata_lines),
            "## Content",
            _collapse_text(body_markdown),
        ]
        return "\n\n".join(section for section in sections if section.strip()) + "\n"

    def import_whitelist(self, output_dir: str | Path, limit: int | None = None, overwrite: bool = False) -> MedicalImportResult:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        entries = self.load_manifest()
        if limit is not None:
            entries = entries[:limit]

        written = 0
        skipped = 0
        failed = 0
        failure_details = []
        for entry in entries:
            stem = entry.get("id") or f"who-{_slugify(entry['title'])}"
            markdown_path = output_path / f"{stem}.md"
            if markdown_path.exists() and not overwrite:
                skipped += 1
                continue
            try:
                html_text = self._download_html(entry)
                article_html = self._extract_article_html(html_text)
                body_markdown = html_to_markdown(article_html)
                if not body_markdown:
                    raise ValueError("WHO article content was empty after HTML conversion.")
                markdown_path.write_text(self._render_entry_markdown(entry, body_markdown), encoding="utf-8")
                written += 1
            except Exception as exc:
                print(f"Failed to import WHO document '{entry.get('title', stem)}': {exc}")
                failed += 1
                failure_details.append(f"{entry.get('title', stem)}: {exc}")

        return MedicalImportResult(
            downloaded=len(entries),
            written=written,
            skipped=skipped,
            output_dir=output_path,
            discovered_url=str(self.manifest_path),
            failed=failed,
            failure_details=failure_details,
        )
