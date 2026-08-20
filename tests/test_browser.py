import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from downloader.browser import BrowserManager
from downloader.config import AppConfig
from downloader.logger import RunLogger


def make_config(timeout=5, headless=True, user_agent="test-agent"):
    return AppConfig(Path("downloads"), timeout, 1, headless, user_agent, logger=RunLogger(False))


class BrowserManagerTests(unittest.TestCase):
    def test_get_creates_and_reuses_driver(self):
        first = MagicMock()
        with patch("downloader.browser.webdriver.Chrome", return_value=first) as chrome:
            manager = BrowserManager()
            config = make_config()

            self.assertIs(manager.get(config), first)
            self.assertIs(manager.get(config), first)

        chrome.assert_called_once()
        first.set_page_load_timeout.assert_called_once_with(5)

    def test_performance_logging_change_recreates_driver(self):
        first, second = MagicMock(), MagicMock()
        with patch("downloader.browser.webdriver.Chrome", side_effect=[first, second]):
            manager = BrowserManager()
            config = make_config()

            manager.get(config)
            self.assertIs(manager.get(config, performance_log=True), second)

        first.quit.assert_called_once_with()

    def test_config_change_recreates_driver(self):
        first, second = MagicMock(), MagicMock()
        with patch("downloader.browser.webdriver.Chrome", side_effect=[first, second]):
            manager = BrowserManager()
            manager.get(make_config(timeout=5))
            self.assertIs(manager.get(make_config(timeout=10)), second)

        first.quit.assert_called_once_with()

    def test_start_failure_does_not_leave_driver(self):
        with patch("downloader.browser.webdriver.Chrome", side_effect=RuntimeError("boom")):
            manager = BrowserManager()
            with self.assertRaisesRegex(RuntimeError, "boom"):
                manager.get(make_config())

            manager.close()
            self.assertIsNone(manager._driver)

    def test_close_is_idempotent(self):
        driver = MagicMock()
        with patch("downloader.browser.webdriver.Chrome", return_value=driver):
            manager = BrowserManager()
            manager.get(make_config())
            manager.close()
            manager.close()

        driver.quit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
