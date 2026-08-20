import unittest
from pathlib import Path
from unittest.mock import patch

from downloader.config import AppConfig
from downloader.logger import RunLogger
from downloader.__main__ import run_module


class MainTests(unittest.TestCase):
    def test_module_failure_is_reported_as_failure(self):
        class BrokenModule:
            def run(self, config):
                raise RuntimeError("boom")

        config = AppConfig(Path("."), 1, 1, False, "test-agent", False, RunLogger(False), {})
        with patch("downloader.__main__.build_registry", return_value={"broken": BrokenModule()}), \
                patch("downloader.__main__.browser.close") as close:
            self.assertFalse(run_module("broken", config, config.logger))
        close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
