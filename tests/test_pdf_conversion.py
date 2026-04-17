import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, r"D:\nageoffer\agentic-rag-for-dummies\project")

from utils import pdf_to_markdown  # noqa: E402


class FakePage:
    def __init__(self, plain_text="", ocr_text="", ocr_languages=None):
        self.plain_text = plain_text
        self.ocr_text = ocr_text
        self.ocr_languages = set(ocr_languages or [])

    def get_text(self, mode, textpage=None):
        if textpage is not None:
            return self.ocr_text
        return self.plain_text

    def get_textpage_ocr(self, language=None, dpi=None, full=None):
        if language not in self.ocr_languages:
            raise RuntimeError(f"language '{language}' unavailable")
        return object()


class FakeDoc:
    def __init__(self, name, pages):
        self.name = name
        self._pages = pages

    def __iter__(self):
        return iter(self._pages)

    def close(self):
        return None


class PdfConversionTests(unittest.TestCase):
    def test_pdf_to_markdown_falls_back_to_plain_text_when_layout_is_too_short(self):
        fake_doc = FakeDoc(
            "sample.pdf",
            [FakePage(plain_text="第一段说明\n第二段说明\n第三段说明")],
        )

        with tempfile.TemporaryDirectory(prefix="pdf-convert-") as temp_dir:
            with mock.patch("utils.pymupdf.open", return_value=fake_doc):
                with mock.patch("utils.pymupdf4llm.to_markdown", return_value="短"):
                    result = pdf_to_markdown("sample.pdf", temp_dir, min_chars=10)

            content = (Path(temp_dir) / "sample.md").read_text(encoding="utf-8")

        self.assertEqual(result.method_used, "plain_text_fallback")
        self.assertIn("Page 1", content)
        self.assertGreater(result.extracted_char_count, 10)

    def test_pdf_to_markdown_uses_ocr_when_plain_text_is_still_too_short(self):
        fake_doc = FakeDoc(
            "ocr.pdf",
            [FakePage(plain_text="", ocr_text="OCR 提取到的正文内容", ocr_languages={"eng"})],
        )

        with tempfile.TemporaryDirectory(prefix="pdf-ocr-") as temp_dir:
            with mock.patch("utils.pymupdf.open", return_value=fake_doc):
                with mock.patch("utils.pymupdf4llm.to_markdown", return_value=""):
                    result = pdf_to_markdown("ocr.pdf", temp_dir, min_chars=8)

            content = (Path(temp_dir) / "ocr.md").read_text(encoding="utf-8")

        self.assertEqual(result.method_used, "ocr_fallback")
        self.assertIn("OCR 提取到的正文内容", content)
        self.assertTrue(any("OCR attempt" in warning for warning in result.warnings))


if __name__ == "__main__":
    unittest.main()
