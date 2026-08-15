"""统一下载框架。"""

from .config import AppConfig
from .registry import build_registry

__all__ = ["AppConfig", "build_registry"]
