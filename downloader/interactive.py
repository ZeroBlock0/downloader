from pathlib import Path

from .config import AppConfig
from .core import DEFAULT_FILTER_PATTERN
from .user_agents import choose_user_agent


def _required(label: str, cast=str, logger=None, minimum=None):
    while True:
        value = input(f"{label}: ").strip()
        if logger:
            logger.input(label, value)
        if value:
            if cast is bool:
                normalized = value.lower()
                if normalized in {"1", "true", "yes", "y", "是"}:
                    return True
                if normalized in {"0", "false", "no", "n", "否"}:
                    return False
                print("请输入 true/false。", flush=True)
                continue
            try:
                converted = cast(value)
                if minimum is not None and converted < minimum:
                    print(f"请输入不小于 {minimum} 的值。", flush=True)
                    continue
                return converted
            except ValueError:
                print("请输入有效值。", flush=True)
        else:
            print("此项不能为空。", flush=True)


def _optional(label: str, cast=str, logger=None, minimum=None):
    while True:
        value = input(f"{label}（直接回车表示无）: ").strip()
        if logger:
            logger.input(label, value)
        if not value:
            return None
        try:
            converted = cast(value)
            if minimum is not None and converted < minimum:
                print(f"请输入不小于 {minimum} 的值。", flush=True)
                continue
            return converted
        except ValueError:
            print("请输入有效值。", flush=True)


def _defaulted(label: str, default, cast=str, logger=None):
    while True:
        value = input(f"{label} [{default}]: ").strip()
        if logger:
            logger.input(label, value or str(default))
        if not value:
            return default
        if cast is bool:
            normalized = value.lower()
            if normalized in {"1", "true", "yes", "y", "是"}:
                return True
            if normalized in {"0", "false", "no", "n", "否"}:
                return False
            print("请输入 true/false。", flush=True)
            continue
        try:
            return cast(value)
        except ValueError:
            print("请输入有效值。", flush=True)


def collect(logger=None) -> tuple[str | None, AppConfig | None]:
    print("\n=== 下载主程序 ===")
    print("1. 画廊滚动采集")
    print("2. 网络日志采集")
    print("3. 随机图 API 图片采集")
    print("0. 退出")
    choices = {"1": "gallery", "2": "network", "3": "random", "0": None}
    while True:
        selection = input("请选择模块: ").strip()
        if logger:
            logger.input("请选择模块", selection)
        if selection in choices:
            module = choices[selection]
            break
        print("无效选择，请输入 0、1、2 或 3。", flush=True)
    if module is None:
        return None, None

    print("\n--- 全局设置 ---")
    output_dir = Path(_defaulted("下载目录", "downloads", logger=logger))
    output_dir.mkdir(parents=True, exist_ok=True)
    enable_md5 = _defaulted("启用全局 MD5 校验", True, bool, logger)
    filter_pattern = _defaulted("全局资源过滤规则", DEFAULT_FILTER_PATTERN, logger=logger)

    print(f"\n--- {module} 模块设置 ---")
    timeout = _required("请求超时秒数", int, logger, 1)
    workers = _required("并发数", int, logger, 1)
    headless = _defaulted("无头浏览器(True/False)", True, bool, logger)
    user_agent = choose_user_agent(logger)
    extra = {}

    if module in {"gallery", "network"}:
        extra["url"] = _required("目标链接", logger=logger)
    if module == "gallery":
        while True:
            extra["mode"] = _required("下载模式(0=流式, 1=批量)", int, logger)
            if extra["mode"] in {0, 1}:
                break
            print("下载模式只能是 0 或 1。", flush=True)
    elif module == "network":
        extra["selector"] = _required("点击按钮 CSS 选择器", logger=logger)
        extra["max_clicks"] = _required("最大点击次数", int, logger, 1)
        extra["idle_seconds"] = _required("无新资源停止秒数", int, logger, 0)
    else:
        extra["apis"] = {
            "pc": _required("PC API URL", logger=logger),
            "mobile": _required("Mobile API URL", logger=logger),
        }
        extra["interval"] = _required("下载间隔秒数", float, logger, 0)
        extra["limit"] = _optional("下载次数", int, logger, 1)

    extra["filter_pattern"] = filter_pattern
    return module, AppConfig(output_dir, timeout, workers, headless, user_agent, enable_md5, logger, extra)
