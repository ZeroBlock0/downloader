from dataclasses import dataclass
from typing import Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from .config import AppConfig


@dataclass
class BrowserManager:
    _driver: Any = None
    _config_key: tuple[Any, ...] | None = None

    def get(self, config: AppConfig, *, performance_log: bool = False):
        key = (config.user_agent, config.browser_headless, config.timeout, performance_log)
        if self._driver is not None and self._config_key != key:
            self.close()
        if self._driver is not None:
            return self._driver

        self._log(config, "浏览器启动中: Chrome")
        options = Options()
        options.page_load_strategy = "eager"
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"user-agent={config.user_agent}")
        options.add_argument("--ignore-certificate-errors")
        if config.browser_headless:
            options.add_argument("--headless=new")
        if performance_log:
            options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        try:
            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(config.timeout)
        except Exception as exc:
            self._driver = None
            self._config_key = None
            self._log(config, f"浏览器启动失败: {exc}")
            raise

        self._driver = driver
        self._config_key = key
        self._log(config, "浏览器启动完成: Chrome")
        return driver

    def close(self) -> None:
        driver, self._driver = self._driver, None
        self._config_key = None
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    def reset(self) -> None:
        self.close()

    @staticmethod
    def _log(config: AppConfig, message: str) -> None:
        if config.logger:
            config.logger.event(message)


browser = BrowserManager()
