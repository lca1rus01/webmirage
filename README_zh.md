# webmirage

**让 AI 拥有搜索和阅读互联网能力的 MCP 服务器。**

网蜃楼 — 帮 AI 从互联网的海市蜃楼中捕捉真实信息。

[English](README.md) | [中文](README_zh.md)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io/)

---

## webmirage 是什么？

webmirage 是一个 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 服务器，将 AI 助手（Claude、Cursor、Windsurf、opencode 等）连接到实时互联网数据 — **无需任何官方 API 或 API 密钥**。

不需要花钱买 Twitter API v2（$100/月）、不需要受限于 Reddit API 的速率限制、不需要雪球的商业数据授权 — webmirage 使用你的浏览器 Cookie 访问与网页前端相同的内部 API，并在 TLS 层面模拟真实浏览器以避免被检测。

### 核心能力

- **社交媒体监控** — 搜索推文、阅读 Reddit 讨论、批量拉取关注列表最新动态
- **金融数据** — 实时股票行情、PE/PB/EPS 估值、热门股票排行（A 股、港股、美股）
- **二手市场** — 搜索闲鱼商品并智能评分排名
- **反检测** — TLS 指纹模拟、`x-client-transaction-id` 生成、请求抖动
- **插件架构** — 实现一个接口即可添加新平台

---

## 支持的平台

### Twitter/X（9 个工具）

| 工具 | 说明 |
|------|------|
| `twitter_search` | 按关键词搜索推文（支持高级搜索语法） |
| `twitter_user_posts` | 获取某用户的最新推文 |
| `twitter_tweet` | 读取特定推文及其回复（对话线程） |
| `twitter_user_profile` | 获取用户画像（简介、粉丝数等） |
| `twitter_me` | 获取自己的资料（无需参数） |
| `twitter_my_following` | 获取自己关注的账号列表 |
| `twitter_following` / `twitter_followers` | 获取任意用户的关注/粉丝列表 |
| `twitter_feed` | 一次性拉取 watchlist 中所有博主的最新推文 |

### Reddit（5 个工具）

| 工具 | 说明 |
|------|------|
| `reddit_search` | 按关键词搜索 Reddit 帖子（支持指定版块） |
| `reddit_subreddit_posts` | 获取版块的热帖/新帖/精华帖 |
| `reddit_post` | 读取特定帖子及其评论（含嵌套回复） |
| `reddit_user_profile` | 获取用户 Karma、账号年龄、简介 |
| `reddit_user_posts` | 获取用户最近的帖子和评论 |

### 雪球 Xueqiu（5 个工具）

| 工具 | 说明 |
|------|------|
| `xueqiu_quote` | 实时行情 + PE/PB/EPS/换手率/市值 |
| `xueqiu_search` | 按名称或代码搜索股票 |
| `xueqiu_hot_posts` | 社区热帖 |
| `xueqiu_hot_stocks` | 人气榜/关注榜 |
| `xueqiu_watchlist` | 自选股批量行情 |

> 支持沪深（SH/SZ）、港股、美股市场。

### 闲鱼 Xianyu / Goofish（5 个工具）

| 工具 | 说明 |
|------|------|
| `xianyu_search_products` | 搜索商品（支持价格区间、个人卖家过滤、排序） |
| `xianyu_score_search` | 搜索 + 智能评分 v3.0（时效性 × 稀缺度矩阵） |
| `xianyu_get_item_detail` | 获取商品完整详情（描述、卖家信息、图片列表） |
| `xianyu_get_items` | 获取自己账号的在售商品列表 |
| `xianyu_confirm_delivery` | 确认订单虚拟发货 |

> 通过 Cookie + mtop H5 API 签名直接 HTTP 调用，无需 Playwright / Node.js。

---

## 快速开始

### 1. 安装

```bash
git clone https://github.com/lca1rus01/webmirage.git
cd webmirage
pip install -e .
```

如需浏览器 Cookie 自动提取功能，安装可选依赖：

```bash
pip install -e ".[xueqiu]"
```

### 2. 配置 Cookie

webmirage 支持两种配置方式（任选其一即可）：

**方式 A：环境变量 / `.env` 文件**

将 `.env.example` 复制为 `.env` 并填入 Cookie：

```bash
cp .env.example .env
```

```ini
# Twitter/X — 登录 x.com 后从浏览器 Cookie 获取
TWITTER_AUTH_TOKEN=your_auth_token
TWITTER_CT0=your_ct0
# TWITTER_PROXY=socks5://127.0.0.1:1080  # 可选代理

# Reddit — 从浏览器获取 reddit_session cookie
# REDDIT_COOKIE=reddit_session=xxx

# 闲鱼/Goofish — 完整 cookie 字符串，需含 _m_h5_tk 和 unb
# XIANYU_COOKIE=your_full_cookie_string
```

**方式 B：YAML 配置文件** 位于 `~/.webmirage/config.yaml`

```yaml
twitter_auth_token: "your_auth_token"
twitter_ct0: "your_ct0"
twitter_watchlist:
  - elonmusk
  - realDonaldTrump

reddit_cookie: "reddit_session=xxx"

xueqiu_watchlist:
  - SH601318
  - 09988
  - AAPL

xianyu_cookie: "_m_h5_tk=xxx; unb=12345; ..."
```

### 3. 如何获取 Cookie

#### Twitter/X
1. 在浏览器中登录 [x.com](https://x.com)
2. 安装 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) Chrome 插件
3. 点击插件图标 -> Export -> "Header String"
4. 从导出内容中找到 `auth_token` 和 `ct0` 两个值

#### Reddit
1. 在 Chrome/Edge 中登录 [reddit.com](https://www.reddit.com)
2. F12 -> Application -> Cookies -> reddit.com
3. 找到 `reddit_session`，复制其 Value
4. 配置为 `reddit_session=xxx` 形式

> 如果安装了 `browser-cookie3`，webmirage 可以自动从浏览器提取 Reddit Cookie — 无需手动配置。

#### 闲鱼 / Goofish
1. 在浏览器中登录 [goofish.com](https://www.goofish.com)
2. F12 -> Application -> Cookies -> goofish.com
3. 把所有 Cookie 拼成 `k1=v1; k2=v2; ...` 格式
4. 必须包含 `_m_h5_tk` 和 `unb` 字段

#### 雪球 / Xueqiu
- 无需 Cookie！webmirage 会自动从雪球首页获取公共 Cookie。
- 如需个性化数据（自选股），在 Chrome 中登录并安装 `browser-cookie3`。

### 4. 添加到 MCP 客户端

**Claude Desktop**（`claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "webmirage": {
      "command": "python",
      "args": ["-m", "webmirage"],
      "cwd": "/path/to/webmirage",
      "env": {
        "TWITTER_AUTH_TOKEN": "your_auth_token",
        "TWITTER_CT0": "your_ct0"
      }
    }
  }
}
```

**Cursor / Windsurf / opencode** — 在 MCP 设置中添加相同的配置。

**或者**，如果你使用 `~/.webmirage/config.yaml` 管理 Cookie，可以省略 `env` 块：

```json
{
  "mcpServers": {
    "webmirage": {
      "command": "python",
      "args": ["-m", "webmirage", "--cwd", "/path/to/webmirage"]
    }
  }
}
```

### 5. 开始使用

直接对你的 AI 助手说：

**Twitter：**
- "搜索 Twitter 上关于 Claude Code 的讨论"
- "获取 @elonmusk 的最新推文"
- "读一下这条推文：https://x.com/..."
- "看看 @sama 的资料"
- "拉取我关注博主的最新推文"

**Reddit：**
- "在 Reddit 上搜索关于 opencode bug 的讨论"
- "r/MachineLearning 有什么热帖？"
- "读一下这个 Reddit 帖子：https://www.reddit.com/r/.../comments/..."
- "看看 u/spez 的资料和最近动态"

**雪球：**
- "查一下 SH600519（茅台）的行情"
- "搜索名字叫'阿里巴巴'的股票"
- "雪球上热门的股票有哪些？"
- "看看我的自选股行情"

**闲鱼：**
- "搜闲鱼上的 16G 迷你主机，按评分排名"
- "查看这个闲鱼商品的详情：<item_id>"
- "看看我闲鱼上挂了哪些东西"
- "给这个订单发货：<order_id>"

---

## 架构

```
webmirage/
├── __main__.py              # 入口：python -m webmirage
├── server.py                # MCP 服务器 — 发现并注册平台工具
├── config.py                # 配置管理（环境变量 + YAML）
└── platforms/
    ├── base.py              # PlatformTools 接口（用于扩展）
    ├── twitter/
    │   ├── graphql.py       # GraphQL queryId 管理、URL 构建
    │   ├── auth.py          # Cookie 认证
    │   ├── client.py        # TwitterClient（TLS 指纹模拟、API 调用）
    │   └── tools.py         # 9 个 MCP 工具定义
    ├── reddit/
    │   ├── client.py        # RedditClient（Cookie + JSON API）
    │   └── tools.py         # 5 个 MCP 工具定义
    ├── xueqiu/
    │   ├── client.py        # XueqiuClient（Cookie + urllib）
    │   └── tools.py         # 5 个 MCP 工具定义（行情/搜索/热帖/热门股/自选股）
    └── xianyu/
        ├── client.py        # XianyuClient（Cookie + mtop 签名直调）
        ├── scorer.py        # 智能评分系统 v3.0（时效×稀缺矩阵 + 规格提取）
        └── tools.py         # 5 个 MCP 工具定义
```

### 技术原理

**Twitter：** 访问 Twitter 的**内部 GraphQL API** — 与 x.com 网页前端使用的 API 相同。反检测技术栈：
1. `curl_cffi` — 模拟 Chrome 的 TLS 握手（JA3/JA4 指纹）
2. `x-client-transaction-id` — 生成有效的交易请求头
3. 完整 Cookie 转发 — 不只是 `auth_token` + `ct0`
4. 请求时序抖动 — 请求间随机延迟
5. 速率限制重试 — HTTP 429 指数退避

**Reddit：** 使用 Reddit 的 `.json` 端点配合 `reddit_session` Cookie。公共端点支持匿名回退。通过 `browser-cookie3` 自动提取浏览器 Cookie。

**雪球：** 调用雪球的公共 JSON API，自动获取 Cookie。访问首页即可获得有效的会话 Cookie 用于公共数据。个性化自选股需要登录 Cookie。

**闲鱼：** 通过 Cookie 认证 + MD5 签名生成（`sign=md5(token&t&appKey&data)`）直接 HTTP 调用阿里巴巴的 mtop H5 API。无需浏览器自动化。

---

## 闲鱼智能评分系统 v3.0

`xianyu_score_search` 工具实现了一套独特的、为人机协作设计的评分系统：

| 维度 | 分值 | 评分方 |
|------|------|--------|
| **时效性** | 30 | 代码自动 |
| **基础合规** | 10 | 代码自动 |
| **性价比** | 60 | AI 横向对比 |

**时效性矩阵** — 新鲜度 × 稀缺度，8 天为方向反转点：
- 新上架 + 想要人少 = 高分（捡漏机会）
- 上架已久 + 想要人少 = 低分（滞销，可能有坑）
- 上架已久 + 想要人多 = 中分（有真实需求）

**规格自动提取** — 从标题和描述中自动识别：
- 芯片：Apple Silicon (M1-M4)、Intel (i3/i5/i7/i9)、AMD Ryzen、骁龙
- 内存 + 存储（如 16+256 -> 16G 内存、256G 存储）
- 成色：全新/99新/9成新/8成新
- 电池健康度、循环次数、保修状态
- 更多（颜色、配件、版本、屏幕规格等）

代码做代码擅长的（数据提取、矩阵评分），把需要跨商品综合判断的性价比留给 AI。

---

## 扩展：添加新平台

1. 创建 `webmirage/platforms/<name>/` 包
2. 在 `tools.py` 中实现 `PlatformTools` 子类：

```python
from ..base import PlatformTools

class MyPlatformTools(PlatformTools):
    name = "myplatform"
    description = "My Platform"

    def is_available(self) -> bool:
        ...

    def get_tool_definitions(self) -> list[dict]:
        ...

    async def handle_call(self, tool_name, arguments) -> str:
        ...
```

3. 在 `webmirage/server.py` 中注册：

```python
ALL_PLATFORMS: list[PlatformTools] = [
    TwitterTools(),
    RedditTools(),
    XueqiuTools(),
    XianyuTools(),
    MyPlatformTools(),   # <- 在这里添加
]
```

---

## 安全说明

- Cookie 仅存储在本地 `~/.webmirage/config.yaml`（或 `.env`）中
- 不向任何第三方上传数据 — 所有请求直接发往目标平台
- 建议使用**小号** — 自动化 API 调用存在封号风险
- 代码完全开源，可审计
- 源码中的 Twitter Bearer token 是 x.com 前端 JavaScript 中**公开嵌入**的 — 非密钥

---

## 依赖要求

- Python 3.10+
- 核心依赖：`mcp`、`curl_cffi`、`xclienttransaction`、`beautifulsoup4`、`loguru`、`pyyaml`
- 可选：`browser-cookie3`（用于 Reddit/雪球的浏览器 Cookie 自动提取）

---

## 开源协议

MIT
