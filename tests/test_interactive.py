import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from downloader.interactive import collect


class InteractiveTests(unittest.TestCase):
    def test_gallery_input_builds_config(self):
        values = iter([
            "1", "downloads", "true", "default-filter", "20", "2", "false", "1",
            "https://example.com/gallery", "1",
        ])
        with patch("builtins.input", side_effect=values):
            module, config = collect()

        self.assertEqual(module, "gallery")
        self.assertEqual(config.output_dir.name, "downloads")
        self.assertTrue(config.enable_md5)
        self.assertEqual(config.extra["mode"], 1)

    def test_blank_output_uses_downloads_and_creates_directory(self):
        values = iter([
            "1", "", "", "", "20", "1", "", "",
            "https://example.com/gallery", "0",
        ])
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                with patch("builtins.input", side_effect=values):
                    module, config = collect()
                self.assertEqual(module, "gallery")
                self.assertEqual(config.output_dir, Path("downloads"))
                self.assertTrue(config.output_dir.is_dir())
                self.assertTrue(config.enable_md5)
                self.assertTrue(config.browser_headless)
                self.assertIn("Chrome", config.user_agent)
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
