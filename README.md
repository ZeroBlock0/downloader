# downloader

基于 `uv` 的可扩展资源下载框架。主程序统一管理参数、下载、存储、校验、日志和浏览器生命周期，业务模块只负责资源采集。

## 快速开始

需要 Python 3.10 或更高版本。

```bash
uv sync
uv run -m downloader
```

不传模块参数时会进入交互菜单：先选择模块，再设置全局下载目录、MD5 和资源过滤规则，最后设置当前模块参数。下载目录直接回车默认为 `downloads`，程序会自动创建该目录；过滤规则直接回车默认匹配常见图片和视频格式。交互输入只在当前运行内存中生效，不会写入配置文件。

日志默认开启，保存到项目根目录的 `logs/YYYYMMDD_HHMMSS.log`，终端输出和用户输入会实时同步写入。使用 `--no-log` 可以关闭日志；MD5 校验默认开启，使用 `--no-md5` 可以关闭。

自动化运行时直接通过命令行传入全部参数，不依赖配置文件：

```bash
# 画廊采集：0=流式下载，1=滚动收集后批量下载
uv run -m downloader gallery \
  --output downloaded_images \
  --timeout 20 \
  --workers 10 \
  --user-agent "Mozilla/5.0" \
  --url https://example.com \
  --mode 1

# 网络日志采集
uv run -m downloader network \
  --output downloaded_images \
  --timeout 20 \
  --workers 10 \
  --user-agent "Mozilla/5.0" \
  --url https://example.com \
  --selector .xgkw9L \
  --pattern '\.(jpg|png|jpeg|webp)(?:\?|$)' \
  --max-clicks 500 \
  --idle-seconds 10

# 随机图 API 图片采集；不指定 limit 时持续运行
uv run -m downloader random \
  --output downloaded_images \
  --timeout 20 \
  --workers 10 \
  --user-agent "Mozilla/5.0" \
  --pc-url https://example.com/pc \
  --mobile-url https://example.com/mobile \
  --pattern '(?:\.(?:jpg|png|mp4|webm)(?:\?|$)|(?:image|video)/)' \
  --interval 2 \
  --limit 20
```

命令行模式要求模块所需参数完整传入，可通过 `uv run -m downloader --help` 查看参数列表。任务结束后会输出完成摘要；使用 `Ctrl+C` 停止持续运行的任务会输出停止提示。

画廊批量模式会在收集阶段逐轮输出扫描到的 `img`、`video`、新增数量、累计数量和页面高度；资源收集完成后才进入并发下载阶段。

例如关闭日志和 MD5：

```bash
uv run -m downloader gallery \
  --no-log --no-md5 \
  --output downloaded_images \
  --timeout 20 \
  --workers 10 \
  --user-agent "Mozilla/5.0" \
  --url https://example.com/gallery \
  --mode 1
```

MD5 是全局下载能力，交互模式只设置一次，命令行的 `--no-md5` 是全局关闭开关。无论使用哪个模块，所有下载文件和子目录都共用当前下载目录根部的 `.md5-index`，例如 `downloads/.md5-index`。启动时会递归扫描下载目录并根据实际文件重建索引，清理已经不存在文件对应的过期记录。相同内容只保存一次；服务器提供 `Content-MD5` 时还会进行远端一致性校验，校验失败会自动重试。

### 网络模块的 `--selector`

`--selector` 是用于定位页面点击按钮的 CSS 选择器。例如：

```bash
--selector .xgkw9L
```

表示查找 `class="xgkw9L"` 的元素并循环点击。这个选择器依赖目标网站页面结构，换网站时通常需要重新检查按钮的 class、id 或其他 CSS 定位方式。

### 参数说明

命令行模式要求对应模块的必需参数完整传入：

- `gallery`：`--output`、`--timeout`、`--workers`、`--user-agent`、`--url`、`--mode`
- `network`：以上通用参数，加上 `--selector`、`--max-clicks`、`--idle-seconds`
- `random`：通用参数，加上 `--pc-url`、`--mobile-url`、`--interval`；`--limit` 可选，不传则持续运行
- 全局 `--pattern`：三个模块共用的资源过滤正则；命令行不传时使用默认图片/视频格式规则，交互模式直接回车也使用默认规则，输入内容则使用自定义规则，匹配时不区分大小写

常用开关：

- `--no-log`：关闭实时日志文件
- `--no-md5`：关闭全局 MD5 去重和索引更新
- `--headless`：使用无头 Chrome

交互模式会提供常用 User-Agent 选项：Chrome Windows/macOS、Firefox Windows、Safari iPhone/iPad、Chrome Android，也可以选择自定义值。全局过滤规则会同时用于 gallery、network 和 random 模块；随机 API 即使 URL 是 `.php`，也会根据响应类型和推导出的真实媒体后缀参与匹配。自动化模式直接传入完整字符串，例如：

```bash
--user-agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
```

运行产生的 `logs/`、下载目录和 `.md5-index` 都属于本地运行数据，不应提交到 Git。

随机图 API 的 URL 可能是 `pc.php` 或 `mobile.php`，但响应内容仍然是图片。程序会优先根据响应的 `Content-Type` 生成后缀，例如 `image/jpeg` 保存为 `.jpg`，不会把 API 路由的 `.php` 当作图片后缀；同时会拒绝默认过滤规则之外的非图片响应。

## 项目结构

```text
downloader/
├── __main__.py   # CLI 参数和主入口
├── interactive.py # 交互式设置
├── registry.py   # 模块注册表
├── modules.py    # gallery、network、random 三个模块
├── core.py       # 下载服务、存储、并发和 MD5 去重
├── logger.py     # 全局实时日志和终端镜像
├── browser.py    # Selenium WebDriver 工厂
└── config.py     # 运行时配置对象
```

## 新增模块

实现一个带有 `run(config)` 方法的模块类，然后在 `downloader/registry.py` 注册。新模块应通过公共 `DownloadService` 下载资源，以自动获得重试、流式写入、MD5 校验和统一日志能力。

## 依赖和锁定

- `pyproject.toml`：项目元数据和依赖声明
- `uv.lock`：锁定依赖版本
- `.venv/`：uv 创建的项目虚拟环境，不提交到 Git
- `tests/`：公共下载、MD5 和日志测试

运行测试：

```bash
uv run python -m unittest discover -s tests -v
```
