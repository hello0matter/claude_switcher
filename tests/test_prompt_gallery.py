import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import prompt_gallery


class PromptGalleryTests(unittest.TestCase):
    def test_samples_go_into_a_day_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = prompt_gallery.allocate_prompt_output(
                temp_dir,
                {
                    "base_url": "https://api.xiaomimimo.com/v1",
                    "model": "mimo-v2.6-pro",
                    "reasoning_effort": "medium",
                    "wire_api": "responses",
                },
                datetime(2026, 10, 23, 15, 30, 45),
            )
        self.assertEqual(path.parent.name, "2026-10-23")
        self.assertTrue(path.name.startswith("20261023-153045_xiaomimimo.com_"))

    def test_galleries_group_sites_and_keep_outer_scroll(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            day = root / "2026-10-23"
            day.mkdir()
            (day / "20261023-153045_xiaomimimo.com_mimo_medium_responses.html").write_text(
                "<html><body>pelican</body></html>", encoding="utf-8"
            )
            (day / "20261023-153112_okai.la_gpt_high_responses.html").write_text(
                "<html><body>other</body></html>", encoding="utf-8"
            )
            (root / "old.html").write_text("<html></html>", encoding="utf-8")
            page = prompt_gallery.refresh_galleries(root)
            global_html = page.read_text(encoding="utf-8")
            day_html = (day / "index.html").read_text(encoding="utf-8")

        self.assertIn("xiaomimimo.com", global_html)
        self.assertIn("okai.la", global_html)
        self.assertIn('src="2026-10-23/20261023-153045_xiaomimimo.com_mimo_medium_responses.html"', global_html)
        self.assertIn("未按天归档", global_html)
        self.assertIn("pointer-events: none", global_html)
        self.assertIn("68vh", global_html)
        self.assertIn('src="20261023-153045_xiaomimimo.com_mimo_medium_responses.html"', day_html)
        self.assertIn("../index.html", day_html)
        self.assertNotIn("old.html", day_html)


if __name__ == "__main__":
    unittest.main()
