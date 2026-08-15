from __future__ import annotations

import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import TextIO


class _TeeStream:
    def __init__(self, terminal: TextIO, log_file: TextIO, lock: threading.Lock):
        self.terminal = terminal
        self.log_file = log_file
        self.lock = lock

    def write(self, text: str) -> int:
        with self.lock:
            written = self.terminal.write(text)
            self.log_file.write(text)
            self.log_file.flush()
        return written

    def flush(self) -> None:
        with self.lock:
            self.terminal.flush()
            self.log_file.flush()

    def __getattr__(self, name):
        return getattr(self.terminal, name)


class RunLogger:
    """将终端输出和用户输入实时复制到本次运行的日志文件。"""

    def __init__(self, enabled: bool = True, root: Path = Path("logs")):
        self.enabled = enabled
        self.root = root
        self.path: Path | None = None
        self._file: TextIO | None = None
        self._stdout = None
        self._stderr = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if not self.enabled:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = self.root / f"{stamp}.log"
        counter = 1
        while True:
            try:
                self._file = self.path.open("x", encoding="utf-8", buffering=1)
                break
            except FileExistsError:
                self.path = self.root / f"{stamp}_{counter}.log"
                counter += 1
        self._stdout, self._stderr = sys.stdout, sys.stderr
        sys.stdout = _TeeStream(sys.stdout, self._file, self._lock)
        sys.stderr = _TeeStream(sys.stderr, self._file, self._lock)
        self.event(f"日志启动: {self.path}")

    def event(self, message: str) -> None:
        if not self.enabled or self._file is None:
            return
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"[{stamp}] {message}\n"
        with self._lock:
            if self._stdout is not None:
                self._stdout.write(line)
                self._stdout.flush()
            self._file.write(line)
            self._file.flush()

    def input(self, prompt: str, value: str) -> None:
        self.event(f"用户输入 | {prompt} => {value}")

    def close(self) -> None:
        if not self.enabled:
            return
        if self._stdout is not None:
            sys.stdout = self._stdout
        if self._stderr is not None:
            sys.stderr = self._stderr
        if self._file is not None:
            self._file.flush()
            self._file.close()
            self._file = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
