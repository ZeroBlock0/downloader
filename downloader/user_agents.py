from __future__ import annotations

from .logger import RunLogger


USER_AGENTS = {
    "1": ("Chrome PC Windows", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "2": ("Chrome PC macOS", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "3": ("Firefox PC Windows", "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"),
    "4": ("Safari iPhone", "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1"),
    "5": ("Safari iPad", "Mozilla/5.0 (iPad; CPU OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1"),
    "6": ("Chrome Android", "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"),
}


def choose_user_agent(logger: RunLogger | None = None) -> str:
    print("\nUser-Agent 选项:")
    for key, (name, _) in USER_AGENTS.items():
        print(f"{key}. {name}")
    print("7. 自定义 User-Agent")
    while True:
        choice = input("请选择 User-Agent [1]: ").strip() or "1"
        if logger:
            logger.input("请选择 User-Agent", choice)
        if choice in USER_AGENTS:
            name, value = USER_AGENTS[choice]
            if logger:
                logger.event(f"User-Agent 已选择: {name}")
            return value
        if choice == "7":
            value = input("请输入自定义 User-Agent: ").strip()
            if logger:
                logger.input("自定义 User-Agent", value)
            if value:
                return value
        print("无效选择，请输入 1-7。", flush=True)
