from __future__ import annotations

import base64
import hashlib
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urljoin, urlparse

import requests

from .config import AppConfig

DEFAULT_FILTER_PATTERN = (
    r"(?:\.(?:jpe?g|png|gif|webp|bmp|tiff?|svg|ico|avif|heic|heif|jxl|"
    r"mp4|webm|mov|avi|mkv|flv|wmv|m4v|3gp|ts|mpeg|mpg|ogv)(?:[?#]|$)|"
    r"(?:image|video)/[a-z0-9.+-]+)"
)


def safe_name(name: str, fallback: str = "download") -> str:
    name = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    if name in {".", ".."}:
        return fallback
    return name[:120] or fallback


@dataclass
class DownloadResult:
    status: str
    url: str = ""
    path: Path | None = None
    digest: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in {"saved", "skipped"}


class Md5Index:
    def __init__(self, root: Path, logger=None):
        self.root = Path(root)
        self.path = self.root / ".md5-index"
        self.logger = logger
        self._lock = threading.Lock()
        self.hashes: set[str] = set()
        self._load()

    def _load(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        indexed = 0
        if self.path.exists():
            try:
                indexed = sum(1 for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip())
            except (OSError, UnicodeError) as exc:
                self._log(f"MD5 索引读取失败，将根据实际文件重建: {exc}")
        scanned = 0
        rebuilt: set[str] = set()
        for file_path in self.root.rglob("*"):
            if not file_path.is_file() or file_path.name in {self.path.name, "hashes.txt"} or file_path.name.endswith(".part"):
                continue
            try:
                digest = file_hash(file_path)
            except OSError:
                continue
            scanned += 1
            rebuilt.add(digest)
        self.hashes = rebuilt
        self._rewrite()
        self._log(f"MD5 索引重建完成: {len(self.hashes)} 条，扫描 {scanned} 个文件，原索引 {indexed} 条")

    def _rewrite(self) -> None:
        with self._lock:
            temporary = self.path.with_name(f".{self.path.name}.part")
            temporary.write_text("".join(f"{digest}\n" for digest in sorted(self.hashes)), encoding="utf-8")
            os.replace(temporary, self.path)

    def contains(self, digest: str) -> bool:
        with self._lock:
            return digest in self.hashes

    def add(self, digest: str) -> bool:
        with self._lock:
            if digest in self.hashes:
                return False
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(f"{digest}\n")
                stream.flush()
            self.hashes.add(digest)
        self._log(f"MD5 索引已更新: {digest}")
        return True

    def _log(self, message: str) -> None:
        if self.logger:
            self.logger.event(message)


class Storage:
    def __init__(self, root: Path, md5_index: Md5Index | None = None, logger=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.md5_index = md5_index
        self.logger = logger
        self._lock = threading.Lock()
        self._reserved: set[Path] = set()

    def reserve_path(self, filename: str) -> Path:
        filename = safe_name(filename, "file.jpg")
        with self._lock:
            path = self.root / filename
            stem, suffix = path.stem, path.suffix
            counter = 1
            while path.exists() or path in self._reserved:
                path = self.root / f"{stem}_{counter}{suffix}"
                counter += 1
            self._reserved.add(path)
            return path

    def release_path(self, path: Path) -> None:
        with self._lock:
            self._reserved.discard(path)

    def save_bytes(self, content: bytes, filename: str, *, enable_md5: bool = True, url: str = "") -> DownloadResult:
        if not content:
            self._log(f"跳过空内容: {url}")
            return DownloadResult("failed", url=url, error="内容为空")
        digest = hashlib.md5(content).hexdigest()
        return self._save_temp(content, filename, digest, enable_md5, url)

    def _save_temp(self, content: bytes, filename: str, digest: str, enable_md5: bool, url: str) -> DownloadResult:
        if enable_md5 and self.md5_index and self.md5_index.contains(digest):
            self._log(f"MD5 一致，跳过保存: {digest} | {url}")
            return DownloadResult("skipped", url=url, digest=digest)
        path = self.reserve_path(filename)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.part")
        try:
            temporary.write_bytes(content)
            os.replace(temporary, path)
            if enable_md5 and self.md5_index and not self.md5_index.add(digest):
                path.unlink(missing_ok=True)
                self._log(f"MD5 一致，删除并发重复文件: {digest} | {url}")
                return DownloadResult("skipped", url=url, digest=digest)
            self._log(f"文件保存成功: {path} | MD5={digest}")
            return DownloadResult("saved", url=url, path=path, digest=digest)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            path.unlink(missing_ok=True)
            self._log(f"文件保存失败: {path} | {exc}")
            return DownloadResult("failed", url=url, digest=digest, error=str(exc))
        finally:
            self.release_path(path)

    def save_stream(self, response, filename: str, *, enable_md5: bool = True, url: str = "", expected_md5: str | None = None) -> DownloadResult:
        path = self.reserve_path(filename)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.part")
        digest = hashlib.md5()
        size = 0
        try:
            with temporary.open("wb") as stream:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    stream.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                stream.flush()
            if size == 0:
                raise ValueError("响应内容为空")
            content_length = response.headers.get("Content-Length")
            if content_length and not response.headers.get("Content-Encoding") and content_length.isdigit() and int(content_length) != size:
                raise ValueError(f"响应长度不一致: expected={content_length}, actual={size}")
            actual_md5 = digest.hexdigest()
            if expected_md5 and not md5_matches(actual_md5, expected_md5):
                temporary.unlink(missing_ok=True)
                self._log(f"远端 MD5 校验失败: expected={expected_md5}, actual={actual_md5} | {url}")
                return DownloadResult("checksum_failed", url=url, digest=actual_md5, error="MD5 不一致")
            if enable_md5 and self.md5_index and self.md5_index.contains(actual_md5):
                temporary.unlink(missing_ok=True)
                self._log(f"MD5 一致，跳过保存: {actual_md5} | {url}")
                return DownloadResult("skipped", url=url, digest=actual_md5)
            os.replace(temporary, path)
            if enable_md5 and self.md5_index and not self.md5_index.add(actual_md5):
                path.unlink(missing_ok=True)
                self._log(f"MD5 一致，删除并发重复文件: {actual_md5} | {url}")
                return DownloadResult("skipped", url=url, digest=actual_md5)
            self._log(f"文件保存成功: {path} | MD5={actual_md5} | size={size}")
            return DownloadResult("saved", url=url, path=path, digest=actual_md5)
        except (OSError, ValueError, requests.RequestException) as exc:
            temporary.unlink(missing_ok=True)
            path.unlink(missing_ok=True)
            self._log(f"流式保存失败: {url} | {exc}")
            return DownloadResult("failed", url=url, error=str(exc))
        finally:
            response.close()
            self.release_path(path)

    def _log(self, message: str) -> None:
        if self.logger:
            self.logger.event(message)


class DownloadService:
    def __init__(self, config: AppConfig, storage: Storage):
        self.config = config
        self.storage = storage

    def fetch(self, url: str, filename: str | None = None, *, depth: int = 0) -> DownloadResult:
        last_error = "未知错误"
        for attempt in range(1, 5):
            try:
                result = self._fetch_once(url, filename, depth)
                if result.status in {"saved", "skipped"}:
                    return result
                last_error = result.error or "MD5 不一致"
                self._log(f"下载结果需要重试（第 {attempt}/4 次）: {url} | {last_error}")
            except requests.RequestException as exc:
                last_error = str(exc)
                self._log(f"请求失败（第 {attempt}/4 次）: {url} | {exc}")
            except (OSError, ValueError) as exc:
                last_error = str(exc)
                self._log(f"下载异常（第 {attempt}/4 次）: {url} | {exc}")
            if attempt < 4:
                delay = 2 ** (attempt - 1)
                self._log(f"{delay} 秒后重试: {url}")
                time.sleep(delay)
        self._log(f"最终下载失败: {url} | {last_error}")
        return DownloadResult("failed", url=url, error=last_error)

    def _fetch_once(self, url: str, filename: str | None, depth: int) -> DownloadResult:
        if depth > 2:
            return DownloadResult("failed", url=url, error="详情页递归层数过深")
        response = requests.get(url, headers={"User-Agent": self.config.user_agent}, timeout=self.config.timeout, stream=True)
        try:
            response.raise_for_status()
        except requests.RequestException:
            response.close()
            raise
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        filter_pattern = self.config.extra.get("filter_pattern")
        if filter_pattern:
            try:
                pattern = re.compile(filter_pattern, re.I)
            except re.error as exc:
                response.close()
                return DownloadResult("failed", url=url, error=f"响应过滤规则无效: {exc}")
            final_url = str(getattr(response, "url", url))
            inferred_extension = extension_for(content_type)
            if not any(pattern.search(value) for value in (content_type, final_url, inferred_extension)):
                response.close()
                self._log(f"跳过不符合过滤规则的响应: {url} | Content-Type={content_type}")
                return DownloadResult("skipped", url=url, error="响应不符合过滤规则")
        if "text/html" in content_type:
            html = response.text
            response.close()
            match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html, re.I)
            match = match or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image', html, re.I)
            if not match:
                self._log(f"跳过 HTML 页面，未找到 og:image: {url}")
                return DownloadResult("skipped", url=url, error="HTML 页面无图片地址")
            return self.fetch(urljoin(url, match.group(1)), filename, depth=depth + 1)
        if content_type and not (content_type.startswith("image/") or content_type.startswith("video/") or "octet-stream" in content_type):
            response.close()
            return DownloadResult("skipped", url=url, error=f"非媒体响应: {content_type}")
        filename = filename_for(url, content_type, filename)
        expected = response.headers.get("Content-MD5") or response.headers.get("X-Checksum-MD5")
        result = self.storage.save_stream(response, filename, enable_md5=self.config.enable_md5, url=url, expected_md5=expected)
        if result.status == "checksum_failed":
            self._log(f"远端 MD5 不一致，将重新下载: {url}")
        return result

    def save_browser_bytes(self, content: bytes, filename: str, url: str = "") -> DownloadResult:
        return self.storage.save_bytes(content, filename, enable_md5=self.config.enable_md5, url=url)

    def _log(self, message: str) -> None:
        if self.config.logger:
            self.config.logger.event(message)


def build_download_service(config: AppConfig, subdirectory: str | None = None) -> DownloadService:
    """Create a module download service with one index at the output root."""
    index = Md5Index(config.output_dir, config.logger) if config.enable_md5 else None
    root = config.output_dir / subdirectory if subdirectory else config.output_dir
    return DownloadService(config, Storage(root, index, config.logger))


def md5_matches(actual_hex: str, expected: str) -> bool:
    expected = expected.strip().strip('"')
    if expected.lower() == actual_hex.lower():
        return True
    try:
        return base64.b64encode(bytes.fromhex(actual_hex)).decode() == expected
    except ValueError:
        return False


def extension_for(content_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
    }.get(content_type.split(";", 1)[0], ".bin")


def filename_for(url: str, content_type: str, filename: str | None = None) -> str:
    """Derive a usable, case-normalized media filename from URL and response type."""
    name = filename or Path(unquote(urlparse(url).path)).name
    media_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".mp4", ".webm"}
    suffix = Path(name).suffix.lower()
    content_extension = extension_for(content_type).lower()
    if not name:
        return f"file_{hashlib.sha1(url.encode()).hexdigest()}{content_extension}"
    if suffix in media_extensions:
        return f"{name[:-len(suffix)]}{suffix}"
    if content_extension != ".bin":
        return f"{name[:-len(suffix)] if suffix else name}{content_extension}"
    return name


def file_hash(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_many(service: DownloadService, urls: Iterable[str], workers: int) -> dict[str, int]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    unique_urls = list(dict.fromkeys(urls))
    stats = {"saved": 0, "skipped": 0, "failed": 0}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(service.fetch, url): url for url in unique_urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                result = future.result()
                stats[result.status if result.status in stats else "failed"] += 1
                print(f"[{result.status}] {result.path.name if result.path else result.error or result.digest}: {url}", flush=True)
            except Exception as exc:
                stats["failed"] += 1
                print(f"[failed] {url}: {exc}", flush=True)
    return stats
