<h1 align="center">🌊 webmirage</h1>

<p align="center">
  <strong>Give your AI Agent the ability to search and read the web</strong>
</p>

<p align="center">
  网蜃楼 — Help AI capture real information from the mirage of the internet
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-green.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-compatible-green.svg?style=for-the-badge" alt="MCP Compatible"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> · <a href="README.md">中文</a> · <a href="#supported-platforms">Platforms</a> · <a href="#design-philosophy">Philosophy</a> · <a href="#xianyu-intelligent-scoring-system-v30">Scoring</a>
</p>

---

## Why do you need webmirage?

AI Agents can already write code, edit docs, and manage projects — but ask one to find something online, and it hits a wall:

- 🐦 "Search Twitter for what people think about this product" → **Can't do it**, Twitter API costs $100/mo
- 📖 "Check Reddit for discussions about this bug" → **403 blocked**, server IP rejected
- 📈 "What's the PE ratio of Kweichow Moutai?" → **Can't get it**, financial data requires payment
- 🛒 "Search Goofish for a used mini PC with good value" → **No API**, only manual browsing
- 🌐 "Read what this webpage says" → **Returns raw HTML**, unreadable

**These aren't hard to implement — but each platform has its own gate: paid APIs, anti-bot blocks, login walls, data cleaning. You'd spend hours configuring tools just to let your Agent read a tweet.**

**webmirage turns this into one MCP server:** Install, add cookies, and your AI can search Twitter, browse Reddit, check stock valuations, and shop on Goofish — 24 tools, one entry point.

---

### ✅ Before you start

| | |
|---|---|
| 💰 **Completely free** | All tools open source, all APIs free. No API keys to apply for |
| 🔒 **Privacy-first** | Cookies stored locally only. Never uploaded. Fully open-source, auditable |
| 🛡️ **Anti-detection** | TLS fingerprint impersonation + x-client-transaction-id + request jitter |
| 🤖 **All MCP clients** | Claude Desktop, Cursor, Windsurf, opencode — anything that supports MCP |
| 🧩 **Plugin architecture** | Add new platforms by implementing one interface, no core changes |

---

## Supported Platforms

| Platform | Tools | Core Capabilities | Config |
|----------|-------|--------------------|--------|
| 🐦 **Twitter/X** | 9 | Search tweets, user posts, tweet threads, profiles, following lists, watchlist feed | Cookie (auth_token + ct0) |
| 📖 **Reddit** | 5 | Search posts, subreddit hot posts, post+comments, user profiles, user activity | Cookie (reddit_session), or browser-cookie3 auto-extract |
| 📈 **Xueqiu** | 5 | Real-time quotes+PE/PB/EPS, stock search, hot posts, hot stocks, watchlist batch | None (auto public cookie) |
| 🛒 **Xianyu/Goofish** | 5 | Product search, intelligent scoring, item details, my items, confirm delivery | Cookie (_m_h5_tk + unb) |
| **Total** | **24** | | |

> 🍪 All platforms use browser cookies — no official APIs needed. Cookies stay local, never uploaded.
>
> ⚠️ **Ban risk:** Platforms like Twitter may detect non-browser API calls. Use a **dedicated secondary account**, not your main one.

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/lca1rus01/webmirage.git
cd webmirage
pip install -e .
```

For browser cookie auto-extraction (Reddit / Xueqiu):

```bash
pip install -e ".[xueqiu]"
```

### 2. Configure Cookies

**Option A: `.env` file**

```bash
cp .env.example .env
# Edit .env, fill in your cookies
```

```ini
TWITTER_AUTH_TOKEN=your_auth_token
TWITTER_CT0=your_ct0
# REDDIT_COOKIE=reddit_session=xxx
# XIANYU_COOKIE=your_full_cookie_string
```

**Option B: YAML config** at `~/.webmirage/config.yaml`

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

### How to Get Cookies

<details>
<summary>Twitter/X</summary>

1. Login to [x.com](https://x.com) in your browser
2. Install [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) Chrome extension
3. Click the extension icon -> Export -> "Header String"
4. Find `auth_token` and `ct0` values

</details>

<details>
<summary>Reddit</summary>

1. Login to [reddit.com](https://www.reddit.com) in Chrome/Edge
2. F12 -> Application -> Cookies -> reddit.com
3. Find `reddit_session`, copy its Value
4. Configure as `reddit_session=xxx`

> With `browser-cookie3` installed, webmirage can auto-extract Reddit cookies from your browser.

</details>

<details>
<summary>Xianyu / Goofish</summary>

1. Login to [goofish.com](https://www.goofish.com) in your browser
2. F12 -> Application -> Cookies -> goofish.com
3. Copy all cookies as `k1=v1; k2=v2; ...` format
4. Must include `_m_h5_tk` and `unb` fields

</details>

<details>
<summary>Xueqiu</summary>

- **No cookie needed!** webmirage auto-obtains public cookies from the homepage.
- For personalized data (watchlist), login in Chrome and install `browser-cookie3`.

</details>

### 3. Add to MCP Client

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

> Using `~/.webmirage/config.yaml` for cookies? Skip the `env` block entirely.

### 4. Use It

Just ask your AI:

**Twitter:**
- "Search Twitter for discussions about Claude Code"
- "Get the latest tweets from @elonmusk"
- "Read this tweet: https://x.com/..."
- "What's my watchlist feed?"

**Reddit:**
- "Search Reddit for discussions about opencode bugs"
- "What's hot in r/MachineLearning?"
- "Read this Reddit post's comments"

**Xueqiu:**
- "What's the PE ratio and market cap of Moutai?"
- "What are the hot stocks on Xueqiu?"
- "Show me my watchlist quotes"

**Xianyu:**
- "搜闲鱼上的 16G 迷你主机，按评分排名"
- "查看这个闲鱼商品的详情"
- "看看我闲鱼上挂了哪些东西"
- "给这个订单发货"

---

## Design Philosophy

**webmirage is not an API wrapper — it's a cookie-driven anti-detection data layer.**

Most tools either use official APIs (expensive, rate-limited, requires approval) or run Playwright browsers (heavy, slow, fragile). webmirage takes a third path: **browser cookies + TLS fingerprint impersonation, calling platforms' internal APIs directly** — the same requests your browser makes when you open a webpage, but usable by AI in the terminal.

### Plugin Architecture

```
webmirage/
├── __main__.py              # Entry point: python -m webmirage
├── server.py                # MCP server — discovers & registers platform tools
├── config.py                # Config management (env vars + YAML)
└── platforms/
    ├── base.py              # PlatformTools interface (implement to add platforms)
    ├── twitter/             # 9 tools — internal GraphQL API + TLS impersonation
    │   ├── graphql.py       #   queryId management (hardcoded → community → JS scan)
    │   ├── auth.py          #   Cookie authentication
    │   ├── client.py        #   curl_cffi Chrome TLS fingerprint
    │   └── tools.py         #   Tool definitions
    ├── reddit/              # 5 tools — JSON API + browser cookie extraction
    │   ├── client.py        #   urllib + CookieJar
    │   └── tools.py         #   Tool definitions
    ├── xueqiu/              # 5 tools — public JSON API + watchlist
    │   ├── client.py        #   Auto public cookie
    │   └── tools.py         #   Quotes/search/hot posts/hot stocks/watchlist
    └── xianyu/              # 5 tools — mtop H5 signature direct call + scoring
        ├── client.py        #   MD5 signature + cookie auth
        ├── scorer.py        #   Scoring system v3.0
        └── tools.py         #   Search/score/detail/my items/delivery
```

### Anti-Detection Stack

| Layer | Technology | Description |
|-------|-----------|-------------|
| TLS fingerprint | `curl_cffi` | Impersonates Chrome JA3/JA4 handshake — platform can't tell it's not a browser |
| Request headers | `x-client-transaction-id` | Twitter frontend JS transaction ID, auto-generated per request |
| Cookies | Full forwarding | Not just `auth_token` + `ct0`, but the complete cookie chain |
| Request rhythm | Random jitter | Random delays between requests, simulating human pacing |
| Rate limiting | Exponential backoff | Auto-retry on HTTP 429 with progressive backoff |

### Platform Strategies

| Platform | Route | Why |
|----------|-------|-----|
| Twitter/X | Internal GraphQL API | Official API v2 costs $100/mo; internal API is the same one x.com uses |
| Reddit | `.json` endpoints + cookie | Anonymous access blocked (403); login cookie is the stable path |
| Xueqiu | Public JSON API | Homepage visit auto-issues cookie; public data needs no login |
| Xianyu | mtop H5 API + MD5 signature | No Playwright/Node.js needed, pure HTTP with `sign=md5(token&t&appKey&data)` |

> 📌 These are current selections based on real-world testing. Platforms change anti-bot, we follow — plugin architecture means swapping a route is one file.

---

## Xianyu Intelligent Scoring System v3.0

The `xianyu_score_search` tool implements a unique scoring system designed for human-AI collaboration:

| Dimension | Score | Who scores | Description |
|-----------|-------|------------|-------------|
| **Timeliness** | 30 | Code (auto) | Freshness x Scarcity matrix, 8-day inflection point |
| **Compliance** | 10 | Code (auto) | Has title/price/description/images/not spam |
| **Value for money** | 60 | AI (assess) | Code provides structured specs, AI does cross-product comparison |

**Timeliness matrix — Freshness x Scarcity:**

```
           0-3 wants   4-10    11-20    20+
  Today       30          25       20      15    ← New + few wants = hidden gem
  2-3 days    27          22       17      12
  4-7 days    20          16       12       8
  8+ days     10          12       14      16    ← Reversal: old + many wants = real demand
```

- **New + few wants** = High score (just listed, not grabbed yet — opportunity)
- **Old + few wants** = Low score (stale listing, something might be wrong)
- **Old + many wants** = Medium score (genuine demand, but might already be taken)

**Spec auto-extraction — from title/description:**

- Chips: Apple Silicon (M1-M4), Intel (i3/i5/i7/i9), AMD Ryzen, Snapdragon
- RAM + Storage: `16+256` -> 16G RAM, 256G Storage
- Condition: 全新/99新/9成新/8成新
- Battery health, cycle count, warranty status
- More: color, accessories, version, screen specs, model...

**Philosophy: Code does what code is good at (extraction, matrix scoring), leaves cross-product comparison to AI.**

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

| Measure | Description |
|---------|-------------|
| 🔒 **Local credentials** | Cookies stored in `~/.webmirage/config.yaml` or `.env` only, never uploaded |
| 👀 **Fully open source** | Transparent code, auditable at any time |
| 🔍 **No intermediary** | All requests go directly to the target platform, no third-party server |
| 🧩 **Pluggable** | Don't trust a component? Swap its platform file, no impact on others |
| 📦 **Public token** | Twitter Bearer token in source is the public one embedded in x.com's JS — not a secret |

> ⚠️ **Ban risk:** Platforms like Twitter may detect non-browser API calls. Use a **dedicated secondary account**. Reasons: 1) Platform may limit/ban accounts making non-browser API calls; 2) Cookies = full login access, a secondary account limits exposure if leaked.

---

## Requirements

- Python 3.10+
- Dependencies: `mcp`, `curl_cffi`, `xclienttransaction`, `beautifulsoup4`, `loguru`, `pyyaml`
- Optional: `browser-cookie3` (for Reddit/Xueqiu browser cookie auto-extraction)

---

## License

MIT
