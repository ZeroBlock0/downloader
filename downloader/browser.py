from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from .config import AppConfig


def create_driver(config: AppConfig, *, performance_log: bool = False):
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
        return webdriver.Chrome(options=options)
    except Exception:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
