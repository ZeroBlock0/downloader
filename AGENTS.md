# Repository Guidelines

## Project Structure & Module Organization

- `downloader/` contains the application package and CLI entry point.
- `downloader/modules.py` implements the gallery, network-log, and random-image modules.
- `downloader/core.py` provides shared downloading, streaming, retries, storage, and MD5 indexing.
- `downloader/interactive.py` and `user_agents.py` implement interactive configuration.
- `tests/` contains the standard-library `unittest` suite.
- `README.md`, `LICENSE`, `pyproject.toml`, and `uv.lock` are maintained project metadata and documentation.
- `downloads/` and `logs/` are runtime data and must not be committed. Leave `ゆらあーと/` untouched.

## Build, Test, and Development Commands

Use `uv` for all Python execution:

```bash
uv sync
uv run -m downloader --help
uv run -m downloader
uv run python -m unittest discover -s tests -v
uv run python -m compileall -q downloader
```

The test command runs the complete suite; `compileall` catches syntax and import errors.

## Coding Style & Naming Conventions

Use Python 3.10+ with four-space indentation, type hints for public interfaces, `snake_case` for functions and variables, `PascalCase` for classes, and short descriptive module names. Prefer the shared `DownloadService` instead of implementing download, retry, streaming, or MD5 logic inside a module. Flush user-visible progress output so it is captured by the real-time logger. No formatter or linter is configured; keep changes PEP 8-compatible and run `git diff --check`.

## Testing Guidelines

Add tests under `tests/` using `unittest`, with files named `test_*.py` and methods named `test_<behavior>`. Cover both success and failure paths, especially retries, response filtering, MD5 deduplication, temporary-file cleanup, and interactive defaults. Do not use live network services in unit tests; mock HTTP and browser dependencies.

## Commit & Pull Request Guidelines

Use concise imperative commit subjects, for example `fix random API extensions` or `update contributor guide`. Pull requests should explain the user-visible change, implementation impact, and verification commands. Include relevant logs or screenshots for CLI behavior changes, and call out changes to CLI arguments or runtime data handling.

## Configuration and Safety

Runtime settings are supplied through CLI arguments or the interactive prompt; do not add a configuration file without an explicit design change. Keep MD5 indexes inside the selected download directory, avoid committing downloaded assets, and never expose credentials or API tokens in logs, tests, or documentation.
