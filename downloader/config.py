from dataclasses import dataclass, field
from pathlib import Path

from .logger import RunLogger


@dataclass
class AppConfig:
    output_dir: Path
    timeout: int
    max_workers: int
    browser_headless: bool
    user_agent: str
    enable_md5: bool = True
    logger: RunLogger | None = None
    extra: dict = field(default_factory=dict)
