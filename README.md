# webmirage

**MCP server that gives AI the ability to search and read the web.**

网蜃楼 — 帮 AI 从互联网的海市蜃楼中捕捉真实信息。

Currently supports **Twitter/X**、**雪球(Xueqiu)**、**闲鱼(Goofish)**. Designed to be extensible to more platforms (Reddit, YouTube, etc.) via a plugin architecture.

## Features

- **MCP Protocol** — Works with Claude Desktop, Cursor, Windsurf, and any MCP-compatible client
- **Twitter/X** — Search tweets, read user posts, get tweet threads, view profiles, watchlist feed
- **雪球(Xueqiu)** — 实时行情、估值(PE/PB/EPS)、股票搜索、热门帖子、热门股票、自选股
- **闲鱼(Goofish)** — 商品搜索、我的在售商品列表、确认订单虚拟发货（cookie+mtop签名直调）
- **Cookie Auth** — Uses your browser cookies, no API keys needed
- **TLS Fingerprint** — `curl_cffi` impersonates Chrome's TLS handshake to avoid detection
- **Anti-Detection** — `x-client-transaction-id` header generation, request jitter, rate limit retry
- **Plugin Architecture** — Add new platforms by implementing one interface

## Quick Start

### 1. Install

```bash
cd D:\python\webmirage
pip install -e .
```

### 2. Configure Twitter Cookies

Get your Twitter cookies:

1. Login to [x.com](https://x.com) in your browser
2. Install [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) Chrome extension
3. Click the extension icon -> Export -> Header String
4. Find `auth_token` and `ct0` values

Create `.env` file:

```ini
TWITTER_AUTH_TOKEN=your_auth_token_here
TWITTER_CT0=your_ct0_here
# Optional: TWITTER_PROXY=socks5://127.0.0.1:1080
```

Or set environment variables directly.

### 3. Add to MCP Client

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "webmirage": {
      "command": "python",
      "args": ["-m", "webmirage"],
      "cwd": "D:\\python\\webmirage",
      "env": {
        "TWITTER_AUTH_TOKEN": "your_auth_token",
        "TWITTER_CT0": "your_ct0"
      }
    }
  }
}
```

**Cursor / Windsurf** — Add the same config in your MCP settings.

### 4. Use It

Just ask your AI:

- "Search Twitter for what people are saying about Claude Code"
- "Get the latest tweets from @elonmusk"
- "Read this tweet: https://x.com/..."
- "Show me the profile of @sama"

## Available Tools

### Twitter/X

| Tool | Description |
|------|-------------|
| `twitter_search` | Search tweets by keyword (supports advanced operators) |
| `twitter_user_posts` | Get a user's recent tweets |
| `twitter_tweet` | Read a specific tweet with replies |
| `twitter_user_profile` | Get user profile (bio, followers, etc.) |
| `twitter_me` / `twitter_my_following` | 自己的资料 / 自己的关注列表 |
| `twitter_following` / `twitter_followers` | 某用户的关注/粉丝列表 |
| `twitter_feed` | 拉取 watchlist 里所有博主的最新推文 |

### 雪球 Xueqiu

| Tool | Description |
|------|-------------|
| `xueqiu_quote` | 实时行情 + PE/PB/EPS/换手率/市值 |
| `xueqiu_search` | 按名称/代码搜股票 |
| `xueqiu_hot_posts` | 社区热帖 |
| `xueqiu_hot_stocks` | 人气榜/关注榜 |
| `xueqiu_watchlist` | 自选股批量行情 |

### 闲鱼 Xianyu/Goofish

参考 [xianyu-openclaw-channel](https://github.com/laozuzhen/xianyu-openclaw-channel) 的接口接入方式：通过 cookie + mtop H5 API 签名（`sign=md5(token&t&appKey&data)`）直接 HTTP 调用，无需 Playwright/Node.js。

| Tool | Description |
|------|-------------|
| `xianyu_search_products` | 搜索闲鱼商品（标题/价格/地区/卖家/链接） |
| `xianyu_get_items` | 获取自己账号的在售商品列表 |
| `xianyu_confirm_delivery` | 确认订单虚拟发货 |

> WebSocket 消息流（自动回复）与 Playwright 商品发布等有状态/重操作不在本平台范围——那些能力属于 xianyu-openclaw-channel 的常驻后端。

## Architecture

```
webmirage/
├── __main__.py              # Entry point: python -m webmirage
├── server.py                # MCP server — discovers & registers platform tools
├── config.py                # Config management (env vars + YAML)
└── platforms/
    ├── base.py              # PlatformTools interface (for extending)
    ├── twitter/
    │   ├── graphql.py       # GraphQL queryId management, URL building
    │   ├── auth.py          # Cookie authentication
    │   ├── client.py        # TwitterClient (TLS impersonation, API calls)
    │   └── tools.py         # MCP tool definitions
    ├── xueqiu/
    │   ├── client.py        # XueqiuClient (cookie + urllib)
    │   └── tools.py         # 行情/搜索/热帖/热门股/自选股
    └── xianyu/
        ├── client.py        # XianyuClient (cookie + mtop 签名直调)
        └── tools.py         # 商品搜索/我的商品/确认发货
```

### How Twitter Data is Fetched

webmirage accesses Twitter's **internal GraphQL API** — the same API that x.com's web frontend uses. It's not the paid Twitter API v2.

**Anti-detection stack:**
1. `curl_cffi` — Impersonates Chrome's TLS handshake (JA3/JA4 fingerprint)
2. `x_client_transaction` — Generates `x-client-transaction-id` header
3. Full cookie forwarding — Not just `auth_token` + `ct0`
4. Request timing jitter — Random delays between requests
5. Rate limit retry — Exponential backoff on HTTP 429

**queryId resolution:**
1. Hardcoded fallback constants (fastest)
2. Community-maintained [twitter-openapi](https://github.com/fa0311/twitter-openapi)
3. JS bundle scanning from x.com homepage

## Extending: Add a New Platform

1. Create `webmirage/platforms/<name>/` package
2. Implement `PlatformTools` subclass in `tools.py`:

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

3. Register in `webmirage/server.py`:

```python
ALL_PLATFORMS: list[PlatformTools] = [
    TwitterTools(),
    MyPlatformTools(),   # <- add here
]
```

## Security

- Cookies stored locally in `~/.webmirage/config.yaml` (file permission 600)
- No data uploaded anywhere — all requests go directly to Twitter
- Use a **dedicated/secondary account** — API calls carry ban risk
- Code is fully open source, auditable

## License

MIT
