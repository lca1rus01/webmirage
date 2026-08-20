<h1 align="center">🌊 webmirage</h1>

<p align="center">
  <strong>给你的 AI Agent 一键装上互联网能力</strong>
</p>

<p align="center">
  网蜃楼 — 帮 AI 从互联网的海市蜃楼中捕捉真实信息
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-green.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-compatible-green.svg?style=for-the-badge" alt="MCP Compatible"></a>
</p>

<p align="center">
  <a href="#快速上手">快速开始</a> · <a href="README_en.md">English</a> · <a href="#支持的平台">支持平台</a> · <a href="#设计理念">设计理念</a> · <a href="#闲鱼智能评分系统">闲鱼评分</a>
</p>

---

## 为什么需要 webmirage？

AI Agent 已经能帮你写代码、改文档、管项目——但你让它去网上找点东西，它就抓瞎了：

- 🐦 "帮我搜一下推特上大家怎么评价这个产品" → **搜不了**，Twitter API 要 $100/月
- 📖 "去 Reddit 上看看有没有人遇到过同样的 bug" → **403 被封**，服务器 IP 被拒
- 📈 "查一下茅台现在的 PE 和市值" → **拿不到**，金融数据要付费
- 🛒 "帮我在闲鱼搜个二手迷你主机，性价比好一点的" → **没法搜**，没有 API 只能手动刷
- 🌐 "帮我看看这个网页写了啥" → **抓回来一堆 HTML 标签**，根本没法读

**这些不难实现，但是需要自己折腾配置**

每个平台都有自己的门槛——要付费的 API、要绕过的封锁、要登录的账号、要清洗的数据。你要一个一个去踩坑、装工具、调配置，光是让 Agent 能读个推特就得折腾半天。

**webmirage 把这件事变成一个 MCP 服务器：**

装好、配好 Cookie，你的 AI 就能搜推特、刷 Reddit、查股票行情、逛闲鱼——24 个工具，一个入口。

---

### ✅ 在你用之前，你可能想知道

| | |
|---|---|
| 💰 **完全免费** | 所有工具开源，所有 API 免费。不花一分钱，不用申请任何 API Key |
| 🔒 **隐私安全** | Cookie 只存在你本地，不上传不外传。代码完全开源，随时可审查 |
| 🛡️ **反检测** | TLS 指纹模拟 + x-client-transaction-id 生成 + 请求抖动，降低被封风险 |
| 🤖 **兼容所有 MCP 客户端** | Claude Desktop、Cursor、Windsurf、opencode……任何支持 MCP 的客户端都能用 |
| 🧩 **插件架构** | 实现一个接口就能添加新平台，不改核心代码 |

---

## 支持的平台

| 平台 | 工具数 | 核心能力 | 怎么配 |
|------|--------|----------|--------|
| 🐦 **Twitter/X** | 9 | 搜索推文、用户帖子、帖子线程、用户画像、关注列表、Watchlist Feed | Cookie（auth_token + ct0） |
| 📖 **Reddit** | 5 | 搜索帖子、版块热帖、帖子+评论、用户画像、用户发帖 | Cookie（reddit_session），或装 browser-cookie3 自动提取 |
| 📈 **雪球** | 5 | 实时行情+PE/PB/EPS、股票搜索、热帖、热门股排行、自选股批量行情 | 无需配置（自动获取公共 Cookie） |
| 🛒 **闲鱼** | 5 | 商品搜索、智能评分排名、商品详情、我的在售列表、确认发货 | Cookie（含 _m_h5_tk + unb） |
| **合计** | **24** | | |

> 🍪 所有平台都用浏览器 Cookie 认证，不需要申请任何官方 API。Cookie 只存你本地，不上传不外传。
>
> ⚠️ **封号风险提醒：** 使用 Cookie 登录的平台（Twitter 等），通过脚本/API 调用**存在被平台检测并封号的风险**。请务必使用**专用小号**，不要用你的主账号。

---

## 快速上手

### 1. 安装

```bash
git clone https://github.com/lca1rus01/webmirage.git
cd webmirage
pip install -e .
```

如需浏览器 Cookie 自动提取（Reddit / 雪球）：

```bash
pip install -e ".[xueqiu]"
```

### 2. 配置 Cookie

**方式 A：`.env` 文件**

```bash
cp .env.example .env
# 编辑 .env，填入你的 Cookie
```

```ini
TWITTER_AUTH_TOKEN=你的auth_token
TWITTER_CT0=你的ct0
# REDDIT_COOKIE=reddit_session=xxx
# XIANYU_COOKIE=你的完整cookie字符串
```

**方式 B：YAML 配置文件** `~/.webmirage/config.yaml`

```yaml
twitter_auth_token: "你的auth_token"
twitter_ct0: "你的ct0"
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

### Cookie 怎么获取？

<details>
<summary>Twitter/X（点击展开）</summary>

1. 在浏览器登录 [x.com](https://x.com)
2. 安装 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) Chrome 插件
3. 点击插件图标 → Export → "Header String"
4. 从导出内容中找到 `auth_token` 和 `ct0` 两个值

</details>

<details>
<summary>Reddit（点击展开）</summary>

1. 在 Chrome/Edge 中登录 [reddit.com](https://www.reddit.com)
2. F12 → Application → Cookies → reddit.com
3. 找到 `reddit_session`，复制其 Value
4. 配置为 `reddit_session=xxx` 形式

> 如果安装了 `browser-cookie3`，webmirage 可以自动从浏览器提取 Reddit Cookie——无需手动配置。

</details>

<details>
<summary>闲鱼 / Goofish（点击展开）</summary>

1. 在浏览器中登录 [goofish.com](https://www.goofish.com)
2. F12 → Application → Cookies → goofish.com
3. 把所有 Cookie 拼成 `k1=v1; k2=v2; ...` 格式
4. 必须包含 `_m_h5_tk` 和 `unb` 字段

</details>

<details>
<summary>雪球（点击展开）</summary>

- **无需配置！** webmirage 自动从雪球首页获取公共 Cookie。
- 如需个性化数据（自选股），在 Chrome 中登录并安装 `browser-cookie3` 即可。

</details>

### 3. 添加到 MCP 客户端

**Claude Desktop**（`claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "webmirage": {
      "command": "python",
      "args": ["-m", "webmirage"],
      "cwd": "/path/to/webmirage",
      "env": {
        "TWITTER_AUTH_TOKEN": "你的auth_token",
        "TWITTER_CT0": "你的ct0"
      }
    }
  }
}
```

**Cursor / Windsurf / opencode** — 在 MCP 设置中添加相同的配置。

> 如果用 `~/.webmirage/config.yaml` 管理 Cookie，可以省略 `env` 块。

### 4. 开始用

直接对 AI 说：

**Twitter：**
- "搜索 Twitter 上关于 Claude Code 的讨论"
- "获取 @elonmusk 的最新推文"
- "读一下这条推文：https://x.com/..."
- "拉取我关注博主的最新推文"

**Reddit：**
- "在 Reddit 上搜索关于 opencode 的讨论"
- "r/MachineLearning 有什么热帖？"
- "读一下这个 Reddit 帖子的评论"

**雪球：**
- "查一下茅台的 PE 和市值"
- "雪球上热门的股票有哪些？"
- "看看我的自选股行情"

**闲鱼：**
- "搜闲鱼上的 16G 迷你主机，按评分排名"
- "查看这个闲鱼商品的详情"
- "看看我闲鱼上挂了哪些东西"
- "给这个订单发货"

---

## 设计理念

**webmirage 不是一个 API 包装层，是一个 Cookie 驱动的反检测数据层。**

市面上的工具要么用官方 API（要钱、要审批、有限速），要么用 Playwright 跑浏览器（重、慢、容易崩）。webmirage 走第三条路：**用浏览器 Cookie + TLS 指纹模拟，直接调平台的内部 API**——跟你在浏览器里打开网页一样的请求，AI 却能在终端里直接用。

### 🔌 每个平台都是独立插件

```
webmirage/
├── __main__.py              # 入口：python -m webmirage
├── server.py                # MCP 服务器 — 发现并注册平台工具
├── config.py                # 配置管理（环境变量 + YAML）
└── platforms/
    ├── base.py              # PlatformTools 接口（实现它就能加新平台）
    ├── twitter/             # 9 个工具 — GraphQL 内部 API + TLS 指纹模拟
    │   ├── graphql.py       #   queryId 管理（硬编码 → 社区源 → JS 扫描）
    │   ├── auth.py          #   Cookie 认证
    │   ├── client.py        #   curl_cffi 模拟 Chrome TLS 握手
    │   └── tools.py         #   工具定义
    ├── reddit/              # 5 个工具 — JSON API + 浏览器 Cookie 提取
    │   ├── client.py        #   urllib + CookieJar
    │   └── tools.py         #   工具定义
    ├── xueqiu/              # 5 个工具 — 公共 JSON API + 自选股
    │   ├── client.py        #   自动获取公共 Cookie
    │   └── tools.py         #   行情/搜索/热帖/热门股/自选股
    └── xianyu/              # 5 个工具 — mtop H5 签名直调 + 智能评分
        ├── client.py        #   MD5 签名 + Cookie 认证
        ├── scorer.py        #   评分系统 v3.0
        └── tools.py         #   搜索/评分/详情/我的商品/发货
```

### 反检测技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| TLS 指纹 | `curl_cffi` | 模拟 Chrome 的 JA3/JA4 握手指纹，平台看不出你不是浏览器 |
| 请求头 | `x-client-transaction-id` | Twitter 前端 JS 生成的事务 ID，每次请求自动生成 |
| Cookie | 完整转发 | 不是只发 `auth_token` + `ct0`，而是完整 Cookie 链 |
| 请求节奏 | 随机抖动 | 请求间随机延迟，模拟人类操作节奏 |
| 限速 | 指数退避 | HTTP 429 自动重试，逐步退避 |

### 各平台技术路线

| 平台 | 路线 | 为什么这么选 |
|------|------|-----------|
| Twitter/X | 内部 GraphQL API | 官方 API v2 要 $100/月；内部 API 跟网页前端用同一个 |
| Reddit | `.json` 端点 + Cookie | 匿名接口被封（403）；登录态 Cookie 是当前最稳路径 |
| 雪球 | 公共 JSON API | 首页访问自动下发 Cookie，公共数据无需登录 |
| 闲鱼 | mtop H5 API + MD5 签名 | 不需要 Playwright/Node.js，纯 HTTP 直调，签名 = `md5(token&t&appKey&data)` |

> 📌 这些都是基于真机实测的当前选型。平台改了反爬我们跟着调，插件架构让换路线只改一个文件。

---

## 闲鱼智能评分系统

`xianyu_score_search` 工具实现了一套独特的、为人机协作设计的评分系统：

| 维度 | 分值 | 评分方 | 说明 |
|------|------|--------|------|
| **时效性** | 30 | 代码自动 | 新鲜度 × 稀缺度组合矩阵，8 天后稀缺方向反转 |
| **基础合规** | 10 | 代码自动 | 有标题/价格/描述/图片/非垃圾 |
| **性价比** | 60 | AI 评估 | 代码提供结构化规格，AI 做跨商品横向对比 |

**时效性矩阵 — 新鲜度 × 稀缺度：**

```
           0-3人想要   4-10人   11-20人   20+人
  今天       30          25       20       15    ← 新+人少=捡漏机会
  2-3天      27          22       17       12
  4-7天      20          16       12        8
  8天+       10          12       14       16    ← 反转：旧+人多=有真实需求
```

- **新 + 想要人少** = 高分（刚上架还没被抢，捡漏机会）
- **旧 + 想要人少** = 低分（挂了好几天没人要，可能有坑）
- **旧 + 想要人多** = 中分（有真实需求，但可能已经被聊走了）

**规格自动提取 — 从标题/描述中识别：**

- 芯片：Apple Silicon（M1-M4）、Intel（i3/i5/i7/i9）、AMD Ryzen、骁龙
- 内存 + 存储：`16+256` → 16G 内存、256G 存储
- 成色：全新/99新/9成新/8成新
- 电池健康度、循环次数、保修状态
- 更多：颜色、配件、版本、屏幕规格、型号……

**设计理念：代码做代码擅长的（提取、矩阵评分），把跨商品综合判断留给 AI。**

---

## 扩展：添加新平台

1. 创建 `webmirage/platforms/<name>/` 包
2. 实现 `PlatformTools` 子类：

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
    MyPlatformTools(),   # ← 在这里添加
]
```

---

## 安全性

| 措施 | 说明 |
|------|------|
| 🔒 **凭据本地存储** | Cookie 只存在你本机 `~/.webmirage/config.yaml` 或 `.env`，不上传不外传 |
| 👀 **完全开源** | 代码透明，随时可审查 |
| 🔍 **无中间服务器** | 所有请求直接发往目标平台，不经过任何第三方 |
| 🧩 **可插拔架构** | 不信任某个组件？换掉对应的 platform 文件即可 |
| 📦 **公钥非密钥** | 源码中的 Twitter Bearer token 是 x.com 前端 JS 公开嵌入的，非密钥 |

> ⚠️ **封号风险：** 使用 Cookie 的平台（Twitter、闲鱼等），建议使用**专用小号**。原因：1) 平台可能检测非浏览器 API 调用导致封号；2) Cookie 等同于完整登录权限，用小号可限制泄露影响范围。

---

## 依赖要求

- Python 3.10+
- 核心：`mcp`、`curl_cffi`、`xclienttransaction`、`beautifulsoup4`、`loguru`、`pyyaml`
- 可选：`browser-cookie3`（Reddit / 雪球的浏览器 Cookie 自动提取）

---

## License

[MIT](LICENSE)
