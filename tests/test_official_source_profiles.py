import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "project"))

from core.official_source_profiles import (  # noqa: E402
    get_official_source_profile,
    list_official_source_profiles,
)


class OfficialSourceProfilesTests(unittest.TestCase):
    def test_profiles_have_user_facing_sync_metadata(self):
        profiles = list_official_source_profiles()

        self.assertEqual([profile.source for profile in profiles], ["medlineplus", "who", "nhc"])
        for profile in profiles:
            with self.subTest(profile=profile.source):
                data = profile.to_dict(manifest_count=3, local_file_count=2)
                self.assertTrue(data["label"])
                self.assertTrue(data["catalog_url"].startswith("https://"))
                self.assertGreaterEqual(data["max_limit"], data["default_limit"])
                self.assertIn(data["expansion_status"], {"broad_source", "curated_manifest"})
                self.assertIn("local_file_count", data)
                self.assertTrue(data["recommended_use"])
                self.assertTrue(data["next_step"])

    def test_get_profile_normalizes_source_name(self):
        profile = get_official_source_profile(" WHO ")

        self.assertIsNotNone(profile)
        self.assertEqual(profile.source, "who")
        self.assertIsNone(get_official_source_profile("unknown"))


if __name__ == "__main__":
    unittest.main()
