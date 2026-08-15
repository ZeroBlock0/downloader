import tempfile
import unittest
from pathlib import Path

from downloader.logger import RunLogger


class LoggerTests(unittest.TestCase):
    def test_logger_flushes_terminal_events_and_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with RunLogger(True, root) as logger:
                print("terminal event", flush=True)
                logger.input("URL", "https://example.com")
                log_path = logger.path
                self.assertIsNotNone(log_path)
                self.assertTrue(log_path.exists())
                self.assertIn("terminal event", log_path.read_text(encoding="utf-8"))
                self.assertIn("https://example.com", log_path.read_text(encoding="utf-8"))

    def test_disabled_logger_creates_no_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with RunLogger(False, Path(directory)) as logger:
                logger.event("not written")
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
