import hashlib
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from downloader.config import AppConfig
from downloader.core import DownloadService, Md5Index, Storage, build_download_service, filename_for, md5_matches


class FakeResponse:
    def __init__(self, content: bytes, headers=None):
        self.content = content
        self.headers = headers or {"Content-Type": "image/png"}

    def iter_content(self, chunk_size):
        yield self.content[:2]
        yield self.content[2:]

    def close(self):
        pass

    def raise_for_status(self):
        pass

    @property
    def text(self):
        return self.content.decode("utf-8")


class CoreTests(unittest.TestCase):
    def test_same_md5_is_skipped_across_module_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = Md5Index(root)
            first = Storage(root / "gallery", index)
            second = Storage(root / "network", index)
            content = b"same-image"

            saved = first.save_stream(FakeResponse(content), "image.png", url="gallery")
            skipped = second.save_stream(FakeResponse(content), "other.png", url="network")

            self.assertEqual(saved.status, "saved")
            self.assertEqual(skipped.status, "skipped")
            self.assertEqual(len(list(root.rglob("*.png"))), 1)

    def test_remote_md5_mismatch_does_not_leave_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = Storage(root, Md5Index(root))
            result = storage.save_stream(
                FakeResponse(b"actual"),
                "image.png",
                url="test",
                expected_md5=hashlib.md5(b"expected").hexdigest(),
            )

            self.assertEqual(result.status, "checksum_failed")
            self.assertEqual(list(root.glob("*.png")), [])
            self.assertEqual(list(root.glob("*.part")), [])

    def test_md5_can_be_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = Md5Index(root)
            storage = Storage(root, index)
            first = storage.save_bytes(b"same", "one.bin", enable_md5=False)
            second = storage.save_bytes(b"same", "two.bin", enable_md5=False)

            self.assertEqual(first.status, "saved")
            self.assertEqual(second.status, "saved")
            self.assertEqual(len(list(root.glob("*.bin"))), 2)

    def test_disabled_md5_does_not_create_root_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "downloads"
            config = AppConfig(root, 2, 1, False, "test-agent", False, None, {})

            build_download_service(config)

            self.assertTrue(root.is_dir())
            self.assertFalse((root / ".md5-index").exists())

    def test_detail_page_relative_og_image_is_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            html = b'<meta property="og:image" content="/assets/photo.png">'
            responses = [
                FakeResponse(html, {"Content-Type": "text/html"}),
                FakeResponse(b"png-content", {"Content-Type": "image/png"}),
            ]
            config = AppConfig(root, 2, 1, False, "test-agent", True, None, {})
            service = DownloadService(config, Storage(root, Md5Index(root)))
            with patch("downloader.core.requests.get", side_effect=responses) as request:
                result = service.fetch("https://example.com/page")

            self.assertEqual(result.status, "saved")
            self.assertEqual(result.path.suffix, ".png")
            self.assertEqual(request.call_args_list[1].args[0], "https://example.com/assets/photo.png")

    def test_api_content_type_controls_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            response = FakeResponse(b"png-content", {"Content-Type": "image/png"})
            config = AppConfig(root, 2, 1, False, "test-agent", False, None, {})
            service = DownloadService(config, Storage(root))
            with patch("downloader.core.requests.get", return_value=response):
                result = service.fetch("https://example.com/random-api")

            self.assertEqual(result.status, "saved")
            self.assertEqual(result.path.suffix, ".png")

    def test_api_php_url_uses_image_content_type_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            response = FakeResponse(b"jpeg-content", {"Content-Type": "image/jpeg"})
            config = AppConfig(root, 2, 1, False, "test-agent", False, None, {})
            service = DownloadService(config, Storage(root))
            with patch("downloader.core.requests.get", return_value=response):
                result = service.fetch("https://example.com/random.php")

            self.assertEqual(result.status, "saved")
            self.assertEqual(result.path.name, "random.jpg")

    def test_filter_pattern_skips_non_matching_api_response(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            response = FakeResponse(b"not-an-image", {"Content-Type": "application/json"})
            config = AppConfig(root, 2, 1, False, "test-agent", False, None, {"filter_pattern": r"^image/"})
            service = DownloadService(config, Storage(root))
            with patch("downloader.core.requests.get", return_value=response):
                result = service.fetch("https://example.com/random.php")

            self.assertEqual(result.status, "skipped")
            self.assertEqual(list(root.glob("*")), [])

    def test_media_suffix_is_case_normalized(self):
        self.assertEqual(filename_for("https://example.com/photo.JPG", "image/jpeg"), "photo.jpg")

    def test_stream_failure_removes_partial_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = Storage(root)

            class BrokenResponse(FakeResponse):
                def iter_content(self, chunk_size):
                    yield b"partial"
                    raise requests.ConnectionError("connection lost")

            result = storage.save_stream(BrokenResponse(b"ignored"), "broken.bin", url="broken")

            self.assertEqual(result.status, "failed")
            self.assertEqual(list(root.glob("*.bin")), [])
            self.assertEqual(list(root.glob("*.part")), [])

    def test_content_md5_base64_is_case_sensitive_and_supported(self):
        digest = hashlib.md5(b"content").hexdigest()
        expected = base64.b64encode(bytes.fromhex(digest)).decode()
        self.assertTrue(md5_matches(digest, expected))
        self.assertFalse(md5_matches(digest, expected.swapcase()))

    def test_corrupt_md5_index_is_rebuilt_from_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".md5-index").write_bytes(b"not-utf8:\xff")
            (root / "image.bin").write_bytes(b"image")
            index = Md5Index(root)

            self.assertIn(hashlib.md5(b"image").hexdigest(), index.hashes)
            self.assertNotIn("not-utf8", index.hashes)

    def test_stale_md5_entries_are_removed_when_index_is_rebuilt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stale = hashlib.md5(b"deleted").hexdigest()
            current = hashlib.md5(b"current").hexdigest()
            (root / ".md5-index").write_text(f"{stale}\n", encoding="utf-8")
            (root / "nested").mkdir()
            (root / "nested" / "image.bin").write_bytes(b"current")

            index = Md5Index(root)

            self.assertNotIn(stale, index.hashes)
            self.assertIn(current, index.hashes)
            self.assertEqual((root / ".md5-index").read_text(encoding="utf-8").strip(), current)


if __name__ == "__main__":
    unittest.main()
