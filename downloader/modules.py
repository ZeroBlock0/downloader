import json
import base64
import random
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .browser import browser
from .config import AppConfig
from .core import DownloadResult, DownloadService, build_download_service, download_many, safe_name


class GalleryModule:
    name = "gallery"

    def run(self, config: AppConfig) -> None:
        url = config.extra["url"]
        mode = int(config.extra["mode"])
        filter_pattern = re.compile(config.extra["filter_pattern"], re.I)
        driver = browser.get(config)
        driver.get(url)
        time.sleep(3)
        folder = safe_name(driver.title, "gallery_download")
        service = build_download_service(config, folder)
        if mode == 0:
            self._stream(driver, service, url, filter_pattern)
        else:
            urls = self._collect(driver, filter_pattern)
            print(f"[gallery] 收集完成，共 {len(urls)} 个资源", flush=True)
            stats = download_many(service, urls, config.max_workers)
            print(f"[gallery] 统计: 成功={stats['saved']} 跳过={stats['skipped']} 失败={stats['failed']}", flush=True)
        print("[gallery] 模块完成。", flush=True)

    def _collect(self, driver, pattern=None) -> set[str]:
        self._click_show_all(driver)
        urls: set[str] = set()
        stable_rounds = 0
        last_height = 0
        round_no = 0
        print("[gallery] 开始扫描并收集资源...", flush=True)
        while stable_rounds < 2:
            round_no += 1
            before = len(urls)
            images = driver.find_elements(By.TAG_NAME, "img")
            videos = driver.find_elements(By.TAG_NAME, "video")
            for image in images:
                candidate = None
                try:
                    parent = driver.execute_script("return arguments[0].parentNode;", image)
                    if parent and parent.tag_name.lower() == "a":
                        candidate = parent.get_attribute("href")
                except Exception:
                    pass
                for attr in ("data-original", "data-full", "data-large", "data-src", "src"):
                    candidate = candidate or image.get_attribute(attr)
                if candidate and (pattern is None or pattern.search(candidate)):
                    urls.add(candidate)
            for video in videos:
                candidate = video.get_attribute("src")
                if candidate and (pattern is None or pattern.search(candidate)):
                    urls.add(candidate)
            driver.execute_script("window.scrollBy(0, 400);")
            time.sleep(1)
            height = driver.execute_script("return window.pageYOffset + window.innerHeight;")
            total = driver.execute_script("return document.body.scrollHeight;")
            stable_rounds = stable_rounds + 1 if height >= total and total == last_height else 0
            last_height = total
            print(
                f"[gallery] 扫描第 {round_no} 轮: img={len(images)} video={len(videos)} "
                f"新增={len(urls) - before} 累计={len(urls)} 页面高度={total} "
                f"稳定轮次={stable_rounds}/2",
                flush=True,
            )
        print(f"[gallery] 扫描结束，共发现 {len(urls)} 个资源", flush=True)
        return urls

    def _stream(self, driver, service: DownloadService, referer: str, pattern=None) -> None:
        seen: set[str] = set()
        stats = {"saved": 0, "skipped": 0, "failed": 0}
        stable_rounds = 0
        last_height = 0
        while stable_rounds < 2:
            elements = driver.find_elements(By.TAG_NAME, "img") + driver.find_elements(By.TAG_NAME, "video")
            for element in elements:
                url = element.get_attribute("src") or element.get_attribute("data-src")
                if not url or url in seen or (pattern and not pattern.search(url)):
                    continue
                seen.add(url)
                result = service.fetch(url)
                stats[result.status if result.status in stats else "failed"] += 1
                if result.status == "failed":
                    fallback = self._browser_fallback(driver, element, service, url)
                    if fallback.ok:
                        stats["failed"] -= 1
                        stats[fallback.status] += 1
                        print(f"[gallery] 浏览器兜底{fallback.status}: {url}", flush=True)
                    else:
                        print(f"[gallery] 浏览器兜底失败: {url}", flush=True)
            driver.execute_script("window.scrollBy(0, 400);")
            time.sleep(0.3)
            height = driver.execute_script("return window.pageYOffset + window.innerHeight;")
            total = driver.execute_script("return document.body.scrollHeight;")
            stable_rounds = stable_rounds + 1 if height >= total and total == last_height else 0
            last_height = total
        print(f"[gallery] 流式统计: 成功={stats['saved']} 跳过={stats['skipped']} 失败={stats['failed']}", flush=True)

    @staticmethod
    def _click_show_all(driver) -> None:
        try:
            buttons = driver.find_elements(By.XPATH, "//*[contains(text(), 'Show all') or contains(text(), 'Show All') or contains(text(), 'Load full')]")
            for button in buttons:
                if button.is_displayed():
                    driver.execute_script("arguments[0].click();", button)
                    time.sleep(2)
                    return
        except Exception as exc:
            print(f"[gallery] 展开按钮失败: {exc}", flush=True)

    @staticmethod
    def _browser_fallback(driver, element, service: DownloadService, url: str) -> DownloadResult:
        filename = safe_name(unquote(Path(urlparse(url).path).name), "browser_image.jpg")
        try:
            result = driver.execute_script("""
                const img = arguments[0];
                try {
                    const canvas = document.createElement('canvas');
                    canvas.width = img.naturalWidth;
                    canvas.height = img.naturalHeight;
                    canvas.getContext('2d').drawImage(img, 0, 0);
                    return canvas.toDataURL('image/jpeg', 0.95);
                } catch (e) { return 'ERROR:' + e.message; }
            """, element)
            if isinstance(result, str) and result.startswith("data:"):
                content = base64.b64decode(result.split(",", 1)[1])
                canvas_name = f"{Path(filename).stem}_browser.png"
                return service.save_browser_bytes(content, canvas_name, url)
        except Exception as exc:
            if service.config.logger:
                service.config.logger.event(f"Canvas 兜底失败: {url} | {exc}")
        try:
            screenshot_name = f"{Path(filename).stem}_screenshot.png"
            return service.save_browser_bytes(element.screenshot_as_png, screenshot_name, url)
        except Exception as exc:
            if service.config.logger:
                service.config.logger.event(f"截图兜底失败: {url} | {exc}")
            return DownloadResult("failed", url=url, error=str(exc))


class NetworkModule:
    name = "network"

    def run(self, config: AppConfig) -> None:
        url = config.extra["url"]
        pattern = re.compile(config.extra["filter_pattern"], re.I)
        self._log(f"[network] 启动，目标: {url}")
        self._log(f"[network] 全局资源过滤规则: {pattern.pattern}")
        driver = browser.get(config, performance_log=True)
        service = build_download_service(config)
        try:
            driver.get(url)
            self._log("[network] 页面加载完成，等待点击按钮...")
            self._log(f"[network] 等待按钮: {config.extra['selector']}")
            max_clicks = int(config.extra["max_clicks"])
            idle_limit = int(config.extra["idle_seconds"])
            seen: set[str] = set()
            stats = {"saved": 0, "skipped": 0, "failed": 0}
            last_new = time.time()
            for count in range(1, max_clicks + 1):
                if seen and time.time() - last_new > idle_limit:
                    self._log(f"[network] {idle_limit} 秒没有新资源，停止采集。")
                    break
                self._log(f"[network] 第 {count}/{max_clicks} 次点击，已发现 {len(seen)} 个资源")
                try:
                    button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, config.extra["selector"])))
                    self._log(f"[network] 找到按钮: {config.extra['selector']}")
                    button.click()
                except StaleElementReferenceException:
                    self._log("[network] 按钮已重新渲染，本轮跳过并重新定位")
                    continue
                time.sleep(1)
                logs = driver.get_log("performance")
                cycle_new = 0
                for entry in logs:
                    try:
                        message = json.loads(entry["message"])["message"]
                        if message["method"] != "Network.responseReceived":
                            continue
                        candidate = message["params"]["response"]["url"]
                        if candidate not in seen and pattern.search(candidate):
                            seen.add(candidate)
                            last_new = time.time()
                            cycle_new += 1
                            self._log(f"[network] 发现新资源: {candidate}")
                            result = service.fetch(candidate)
                            stats[result.status if result.status in stats else "failed"] += 1
                            self._log(f"[network] 下载结果: {result.status} | {candidate}")
                    except (KeyError, TypeError, ValueError):
                        continue
                self._log(f"[network] 本轮读取 {len(logs)} 条日志，新增 {cycle_new} 个，累计 {len(seen)} 个")
            self._log(f"[network] 采集结束，共发现 {len(seen)} 个资源。")
            self._log(f"[network] 统计: 成功={stats['saved']} 跳过={stats['skipped']} 失败={stats['failed']}")
        finally:
            self._log("[network] 浏览器任务结束。")

    @staticmethod
    def _log(message: str) -> None:
        print(message, flush=True)


class RandomImageApiModule:
    name = "random"

    def run(self, config: AppConfig) -> None:
        apis = config.extra["apis"]
        service = build_download_service(config)
        self._log(f"[random-image] 全局资源过滤规则: {config.extra['filter_pattern']}")
        interval = float(config.extra["interval"])
        limit = config.extra.get("limit")
        count = 0
        stats = {"saved": 0, "skipped": 0, "failed": 0}
        while limit is None or count < int(limit):
            mode = random.choice(list(apis))
            try:
                result = service.fetch(apis[mode])
                stats[result.status if result.status in stats else "failed"] += 1
                print(f"[random-image] {result.status}: {mode}", flush=True)
            except Exception as exc:
                stats["failed"] += 1
                print(f"[random-image] 采集失败: {exc}", flush=True)
            count += 1
            time.sleep(interval)
        print(f"[random-image] 采集完成: 成功={stats['saved']} 跳过={stats['skipped']} 失败={stats['failed']}", flush=True)

    @staticmethod
    def _log(message: str) -> None:
        print(message, flush=True)
