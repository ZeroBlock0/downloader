from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from .config import AppConfig
from .browser import browser
from .core import DEFAULT_FILTER_PATTERN
from .interactive import collect
from .logger import RunLogger
from .registry import build_registry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="可扩展资源下载框架")
    parser.add_argument("module", nargs="?", choices=build_registry(), help="要运行的模块；不填则进入交互菜单")
    parser.add_argument("--no-log", action="store_true", help="关闭全局实时日志")
    parser.add_argument("--no-md5", action="store_true", help="关闭全局 MD5 校验")
    parser.add_argument("--output", help="统一输出目录")
    parser.add_argument("--timeout", type=int)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--user-agent")
    parser.add_argument("--url", help="gallery/network 模块的目标 URL")
    parser.add_argument("--mode", type=int, choices=(0, 1), help="gallery: 0 流式，1 批量")
    parser.add_argument("--selector", help="network 模块的点击按钮 CSS 选择器")
    parser.add_argument("--pattern", default=DEFAULT_FILTER_PATTERN, help="全局资源过滤正则，默认匹配常见图片和视频格式")
    parser.add_argument("--max-clicks", type=int)
    parser.add_argument("--idle-seconds", type=int)
    parser.add_argument("--pc-url", help="随机图 API 图片采集的 PC API URL")
    parser.add_argument("--mobile-url", help="随机图 API 图片采集的 Mobile API URL")
    parser.add_argument("--interval", type=float)
    parser.add_argument("--limit", type=int, help="随机图 API 图片采集次数")
    return parser


def main() -> None:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--no-log", action="store_true")
    pre_args, _ = pre_parser.parse_known_args()
    logger = RunLogger(enabled=not pre_args.no_log)
    with logger:
        try:
            args = build_parser().parse_args()
            logger.event(f"程序启动，日志={'关闭' if args.no_log else '开启'}")
            logger.event("命令行参数: " + " ".join(sys.argv[1:]))
            if not run_args(args, logger):
                raise SystemExit(1)
        except KeyboardInterrupt:
            print("\n程序已由用户停止。", flush=True)
            logger.event("用户中断程序")
        except SystemExit:
            raise
        except Exception:
            error = traceback.format_exc()
            logger.event("未处理异常:\n" + error)
            print("程序发生未处理异常，详细信息已写入日志。", flush=True)
            raise SystemExit(1)


def run_args(args, logger: RunLogger) -> bool:
    if args.module is None:
        module, config = collect(logger)
        if module is None:
            logger.event("用户选择退出")
            return True
        if args.no_md5:
            config.enable_md5 = False
            logger.event("命令行参数覆盖交互设置：MD5 已关闭")
        return run_module(module, config, logger)

    required = {
        "gallery": ("output", "timeout", "workers", "user_agent", "url", "mode"),
        "network": ("output", "timeout", "workers", "user_agent", "url", "selector", "max_clicks", "idle_seconds"),
        "random": ("output", "timeout", "workers", "user_agent", "pc_url", "mobile_url", "interval"),
    }[args.module]
    missing = [name.replace("_", "-") for name in required if getattr(args, name) is None]
    if missing:
        build_parser().error(f"{args.module} 模块缺少参数: {', '.join('--' + name for name in missing)}")
    invalid = []
    if args.timeout <= 0:
        invalid.append("--timeout 必须大于 0")
    if args.workers <= 0:
        invalid.append("--workers 必须大于 0")
    if args.max_clicks is not None and args.max_clicks <= 0:
        invalid.append("--max-clicks 必须大于 0")
    if args.idle_seconds is not None and args.idle_seconds < 0:
        invalid.append("--idle-seconds 不能小于 0")
    if args.interval is not None and args.interval < 0:
        invalid.append("--interval 不能小于 0")
    if args.limit is not None and args.limit <= 0:
        invalid.append("--limit 必须大于 0")
    if invalid:
        build_parser().error("；".join(invalid))

    extra = {
        "url": args.url,
        "mode": args.mode,
        "selector": args.selector,
        "pattern": args.pattern,
        "filter_pattern": args.pattern,
        "max_clicks": args.max_clicks,
        "idle_seconds": args.idle_seconds,
        "interval": args.interval,
        "limit": args.limit,
        "apis": {"pc": args.pc_url, "mobile": args.mobile_url},
    }
    config = AppConfig(
        output_dir=Path(args.output),
        timeout=args.timeout,
        max_workers=args.workers,
        browser_headless=args.headless,
        user_agent=args.user_agent,
        enable_md5=not args.no_md5,
        logger=logger,
        extra=extra,
    )
    return run_module(args.module, config, logger)


def run_module(module_name: str, config: AppConfig, logger: RunLogger) -> bool:
    try:
        logger.event(f"模块启动: {module_name}，MD5={'开启' if config.enable_md5 else '关闭'}")
        build_registry()[module_name].run(config)
        print(f"\n[{module_name}] 下载任务已完成。", flush=True)
        logger.event(f"模块完成: {module_name}")
        return True
    except KeyboardInterrupt:
        print(f"\n[{module_name}] 用户停止任务。", flush=True)
        logger.event(f"模块被用户停止: {module_name}")
        return False
    except Exception:
        error = traceback.format_exc()
        logger.event(f"模块异常: {module_name}\n{error}")
        print(f"\n[{module_name}] 任务异常，详细信息已写入日志。", flush=True)
        return False
    finally:
        browser.close()


if __name__ == "__main__":
    main()
