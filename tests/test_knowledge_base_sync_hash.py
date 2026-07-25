import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

from core.knowledge_base_sync import KnowledgeBaseSyncService as KBS  # noqa: E402


class ContentHashTests(unittest.TestCase):
    """The content hash drives incremental sync: same content -> skip re-index,
    changed content -> replace chunks.  A too-sensitive hash re-indexes needlessly;
    a too-loose hash silently drops real updates."""

    def test_identical_content_same_hash(self):
        self.assertEqual(KBS._content_hash("# Title\n\nBody text."),
                         KBS._content_hash("# Title\n\nBody text."))

    def test_whitespace_normalization_is_stable(self):
        # Trailing spaces + extra blank lines must not change the hash.
        a = KBS._content_hash("# Title\n\nBody text.")
        b = KBS._content_hash("# Title   \n\n\n\nBody text.  \n")
        self.assertEqual(a, b)

    def test_crlf_and_lf_produce_same_hash(self):
        self.assertEqual(KBS._content_hash("line1\nline2"),
                         KBS._content_hash("line1\r\nline2"))

    def test_real_content_change_changes_hash(self):
        self.assertNotEqual(KBS._content_hash("# Hypertension\n\n130/80"),
                            KBS._content_hash("# Hypertension\n\n140/90"))


class FrontMatterTests(unittest.TestCase):
    def test_extract_front_matter_metadata(self):
        raw = "Source: WHO\nTitle: Hypertension\nSource type: public_health\n\n# Body"
        meta = KBS._extract_front_matter_metadata(raw)
        self.assertEqual(meta["source"], "WHO")
        self.assertEqual(meta["title"], "Hypertension")
        self.assertEqual(meta["source_type"], "public_health")

    def test_strip_front_matter_removes_header(self):
        raw = "Source: WHO\nTitle: X\n\n# Body\n\nContent."
        body = KBS._strip_front_matter(raw)
        self.assertNotIn("Source: WHO", body)
        self.assertIn("# Body", body)

    def test_first_heading(self):
        self.assertEqual(KBS._first_heading("# Diabetes\n\ntext"), "Diabetes")

    def test_first_heading_none(self):
        self.assertEqual(KBS._first_heading("no heading here"), "")


class ClassifyExistingMarkdownTests(unittest.TestCase):
    def test_official_source_key_prefix(self):
        origin, key = KBS._classify_existing_markdown(
            Path("medlineplus-a1c.md"), {"source_key": "official:medlineplus:a1c"})
        self.assertEqual(origin, "official")
        self.assertEqual(key, "official:medlineplus:a1c")

    def test_who_by_source_name(self):
        origin, key = KBS._classify_existing_markdown(
            Path("who-hypertension.md"), {"source": "World Health Organization"})
        self.assertEqual(origin, "official")
        self.assertTrue(key.startswith("official:who:"))

    def test_nhc_by_url(self):
        origin, key = KBS._classify_existing_markdown(
            Path("nhc-doc.md"), {"original_url": "http://www.gov.cn/xxx"})
        self.assertEqual(origin, "official")
        self.assertTrue(key.startswith("official:nhc:"))

    def test_local_fallback(self):
        origin, key = KBS._classify_existing_markdown(Path("my-notes.md"), {})
        self.assertEqual(origin, "local")
        self.assertEqual(key, "local:my-notes.md")


if __name__ == "__main__":
    unittest.main()
