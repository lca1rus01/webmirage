# webmirage

**MCP server that gives AI the ability to search and read the web.**

网蜃楼 — 帮 AI 从互联网的海市蜃楼中捕捉真实信息。

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io/)

---

## What is webmirage?

webmirage is a [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that connects AI assistants (Claude, Cursor, Windsurf, opencode, etc.) to real-time web data — **without any official APIs or API keys**.

Instead of paying for Twitter API v2 ($100/mo), Reddit API (rate-limited), or Xueqiu commercial data feeds, webmirage uses your browser cookies to access the same internal APIs that the web frontends use. It impersonates a real browser at the TLS level to avoid detection.

### Key capabilities

- **Social media monitoring** — Search tweets, read Reddit discussions, monitor watchlists
- **Financial data** — Real-time stock quotes, PE/PB/EPS valuations, hot stock rankings (Chinese A-share, HK, US)
- **Secondhand marketplace** — Search and rank Goofish (闲鱼) products with an intelligent scoring system
- **Anti-detection** — TLS fingerprint impersonation, `x-client-transaction-id` generation, request jitter
- **Plugin architecture** — Add new platforms by implementing one interface

---

## Supported Platforms

### Twitter/X (9 tools)

| Tool | Description |
|------|-------------|
| `twitter_search` | Search tweets by keyword (supports advanced operators) |
| `twitter_user_posts` | Get a user's recent tweets |
| `twitter_tweet` | Read a specific tweet with replies (thread) |
| `twitter_user_profile` | Get user profile (bio, followers, etc.) |
| `twitter_me` | Get your own profile (no params needed) |
| `twitter_my_following` | Get accounts you follow |
| `twitter_following` / `twitter_followers` | Get any user's follow list |
| `twitter_feed` | Fetch latest tweets from all watchlist accounts at once |

### Reddit (5 tools)

| Tool | Description |
|------|-------------|
| `reddit_search` | Search Reddit posts by keyword (supports subreddit filter) |
| `reddit_subreddit_posts` | Get hot/new/top posts from a subreddit |
| `reddit_post` | Read a specific post with comments and nested replies |
| `reddit_user_profile` | Get user karma, account age, bio |
| `reddit_user_posts` | Get a user's recent posts and comments |

### Xueqiu / 雪球 (5 tools)

| Tool | Description |
|------|-------------|
| `xueqiu_quote` | Real-time quote with PE/PB/EPS/turnover/market cap |
| `xueqiu_search` | Search stocks by name or code |
| `xueqiu_hot_posts` | Trending community posts |
| `xueqiu_hot_stocks` | Popularity/attention rankings |
| `xueqiu_watchlist` | Batch quotes for your configured watchlist |

> Supports Shanghai (SH), Shenzhen (SZ), Hong Kong, and US markets.

### Xianyu / 闲鱼 / Goofish (5 tools)

| Tool | Description |
|------|-------------|
| `xianyu_search_products` | Search products with filters (price range, personal sellers, sort) |
| `xianyu_score_search` | Search + intelligent scoring v3.0 (freshness × scarcity matrix) |
| `xianyu_get_item_detail` | Get full item details (description, seller info, images) |
| `xianyu_get_items` | List your own items for sale |
| `xianyu_confirm_delivery` | Confirm virtual delivery for an order |

> Cookie + mtop H5 API signature direct call — no Playwright/Node.js needed.

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/lca1rus01/webmirage.git
cd webmirage
pip install -e .
```

Or install optional dependencies for browser cookie auto-extraction:

```bash
pip install -e ".[xueqiu]"
```

### 2. Configure Cookies

webmirage reads configuration from two sources (both optional, either one works):

**Option A: Environment variables / `.env` file**

Copy `.env.example` to `.env` and fill in your cookies:

```bash
cp .env.example .env
```

```ini
# Twitter/X — get from browser cookies after logging in to x.com
TWITTER_AUTH_TOKEN=your_auth_token
TWITTER_CT0=your_ct0
# TWITTER_PROXY=socks5://127.0.0.1:1080  # optional proxy

# Reddit — get reddit_session cookie from browser
# REDDIT_COOKIE=reddit_session=xxx

# Xianyu/Goofish — full cookie string with _m_h5_tk and unb
# XIANYU_COOKIE=your_full_cookie_string
```

**Option B: YAML config file** at `~/.webmirage/config.yaml`

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

### 3. How to Get Cookies

#### Twitter/X
1. Login to [x.com](https://x.com) in your browser
2. Install [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) Chrome extension
3. Click the extension icon -> Export -> "Header String"
4. Find `auth_token` and `ct0` values

#### Reddit
1. Login to [reddit.com](https://www.reddit.com) in Chrome/Edge
2. F12 -> Application -> Cookies -> reddit.com
3. Find `reddit_session`, copy its Value
4. Configure as `reddit_session=xxx`

> If `browser-cookie3` is installed, webmirage can auto-extract Reddit cookies from your browser — no manual config needed.

#### Xianyu/Goofish
1. Login to [goofish.com](https://www.goofish.com) in your browser
2. F12 -> Application -> Cookies -> goofish.com
3. Copy all cookies as `k1=v1; k2=v2; ...` format
4. Must include `_m_h5_tk` and `unb` fields

#### Xueqiu / 雪球
- No cookie needed! webmirage auto-obtains public cookies from the homepage.
- For personalized data (watchlist), login in Chrome and install `browser-cookie3`.

### 4. Add to MCP Client

**Claude Desktop** (`claude_desktop_config.json`):

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

**Cursor / Windsurf / opencode** — Add the same config in your MCP settings.

**Alternatively**, if you use `~/.webmirage/config.yaml` for cookies, you can skip the `env` block entirely:

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

### 5. Use It

Just ask your AI assistant:

**Twitter:**
- "Search Twitter for what people are saying about Claude Code"
- "Get the latest tweets from @elonmusk"
- "Read this tweet: https://x.com/..."
- "Show me the profile of @sama"
- "What's my watchlist feed?"

**Reddit:**
- "Search Reddit for discussions about opencode bugs"
- "What's hot in r/MachineLearning?"
- "Read this Reddit post: https://www.reddit.com/r/.../comments/..."
- "Show me u/spez's profile and recent activity"

**Xueqiu:**
- "Get the quote for SH600519 (茅台)"
- "Search for stocks named '阿里巴巴'"
- "What are the hot stocks on Xueqiu?"
- "Show me my watchlist quotes"

**Xianyu:**
- "搜闲鱼上的 16G 迷你主机，按评分排名"
- "查看这个闲鱼商品的详情: <item_id>"
- "看看我闲鱼上挂了哪些东西"
- "给这个订单发货: <order_id>"

---

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
    │   └── tools.py         # 9 MCP tool definitions
    ├── reddit/
    │   ├── client.py        # RedditClient (cookie + JSON API)
    │   └── tools.py         # 5 MCP tool definitions
    ├── xueqiu/
    │   ├── client.py        # XueqiuClient (cookie + urllib)
    │   └── tools.py         # 5 MCP tool definitions (quote/search/hot/watchlist)
    └── xianyu/
        ├── client.py        # XianyuClient (cookie + mtop 签名直调)
        ├── scorer.py        # 智能评分系统 v3.0 (时效×稀缺矩阵 + 规格提取)
        └── tools.py         # 5 MCP tool definitions
```

### How It Works

**Twitter:** Accesses Twitter's **internal GraphQL API** — the same API that x.com's web frontend uses. Anti-detection stack:
1. `curl_cffi` — Impersonates Chrome's TLS handshake (JA3/JA4 fingerprint)
2. `x-client-transaction-id` — Generates valid transaction headers
3. Full cookie forwarding — Not just `auth_token` + `ct0`
4. Request timing jitter — Random delays between requests
5. Rate limit retry — Exponential backoff on HTTP 429

**Reddit:** Uses Reddit's `.json` endpoints with `reddit_session` cookie. Anonymous fallback for public endpoints. Browser cookie auto-extraction via `browser-cookie3`.

**Xueqiu:** Calls Xueqiu's public JSON API with auto-obtained cookies. Homepage visit yields a valid session cookie for public data. Login cookies required for personalized watchlist.

**Xianyu:** Direct HTTP calls to Alibaba's mtop H5 API with cookie-based authentication and MD5 signature generation (`sign=md5(token&t&appKey&data)`). No browser automation needed.

---

## Xianyu Intelligent Scoring System v3.0

The `xianyu_score_search` tool implements a unique scoring system designed for human-AI collaboration:

| Dimension | Score | Who scores |
|-----------|-------|------------|
| **Timeliness** | 30 | Code (automatic) |
| **Compliance** | 10 | Code (automatic) |
| **Value for money** | 60 | AI (cross-product comparison) |

**Timeliness matrix** — Freshness × Scarcity, with 8-day inflection point:
- New + few wants = High score (hidden gem opportunity)
- Old + few wants = Low score (stale listing, something wrong)
- Old + many wants = Medium score (genuine demand confirmed)

**Spec extraction** — Automatically extracts from title/description:
- Chips: Apple Silicon (M1-M4), Intel (i3/i5/i7/i9), AMD Ryzen, Snapdragon
- RAM + Storage (e.g., 16+256 -> 16G RAM, 256G Storage)
- Condition: 全新/99新/9成新/8成新
- Battery health, cycle count, warranty status
- And more (color, accessories, version, screen specs, etc.)

The code does what code is good at (data extraction, matrix scoring), and leaves the nuanced cross-product comparison to the AI.

---

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
    RedditTools(),
    XueqiuTools(),
    XianyuTools(),
    MyPlatformTools(),   # <- add here
]
```

---

## Security

- Cookies stored locally in `~/.webmirage/config.yaml` (or `.env`)
- No data uploaded anywhere — all requests go directly to the target platform
- Use a **dedicated/secondary account** — automated API calls carry ban risk
- Code is fully open source, auditable
- The Twitter Bearer token in source code is the **public** token embedded in x.com's JavaScript — it's not a secret

---

## Requirements

- Python 3.10+
- Dependencies: `mcp`, `curl_cffi`, `xclienttransaction`, `beautifulsoup4`, `loguru`, `pyyaml`
- Optional: `browser-cookie3` (for Reddit/Xueqiu browser cookie auto-extraction)

---

## License

MIT
