"""MCP tool definitions for the Xueqiu (雪球) platform.

Exposes five tools to AI agents:
    - xueqiu_quote       : Get real-time stock quote with PE/PB/EPS
    - xueqiu_search       : Search stocks by name or code
    - xueqiu_hot_posts    : Get trending posts from Xueqiu community
    - xueqiu_hot_stocks   : Get hot stock rankings (人气榜/关注榜)
    - xueqiu_watchlist    : Get quotes for all stocks in your watchlist
"""

from __future__ import annotations

import logging
from typing import Any

from loguru import logger

from ..base import PlatformTools
from ... import config as cfg
from .client import XueqiuClient, XueqiuError

logger = logging.getLogger(__name__)


class XueqiuTools(PlatformTools):
    """Xueqiu (雪球) platform tools for webmirage MCP server."""

    name = "xueqiu"
    description = "雪球股票行情、搜索、热门帖子与热门股票排行"

    def __init__(self) -> None:
        self._client: XueqiuClient | None = None

    def is_available(self) -> bool:
        """Xueqiu is always available - homepage fallback yields public cookies."""
        return True

    def _get_client(self) -> XueqiuClient:
        """Get or create a lazy-initialized XueqiuClient."""
        if self._client is None:
            config = cfg.get_config()
            self._client = XueqiuClient(
                cookie_str=config.get("xueqiu_cookie", ""),
            )
        return self._client

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return the five MCP tool definitions."""
        return [
            {
                "name": "xueqiu_quote",
                "description": (
                    "Get real-time stock quote from Xueqiu (雪球). "
                    "Returns price, change, volume, market cap, and key "
                    "valuation metrics: PE (TTM & forecast), PB, EPS, "
                    "turnover rate.\n\n"
                    "Use this when the user wants to:\n"
                    "- Check a stock's current price and valuation\n"
                    "- Compare PE/PB across stocks\n"
                    "- Verify if a stock is 'cheap' or 'expensive'\n"
                    "- Monitor portfolio holdings\n\n"
                    "Symbol formats:\n"
                    "- Shanghai: SH600519 (e.g. SH601318 = 中国平安)\n"
                    "- Shenzhen: SZ000858 (e.g. SZ000858 = 五粮液)\n"
                    "- Hong Kong: 09988 (e.g. 09988 = 阿里巴巴)\n"
                    "- US: AAPL (e.g. AAPL = Apple)"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock code: SH600519, SZ000858, 09988, AAPL, etc.",
                        },
                    },
                    "required": ["symbol"],
                },
            },
            {
                "name": "xueqiu_search",
                "description": (
                    "Search stocks on Xueqiu by name or code. "
                    "Returns matching stocks with symbol, name, and exchange.\n\n"
                    "Use this when the user wants to:\n"
                    "- Find the stock code for a company name\n"
                    "- Look up a stock by partial name"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Stock name or code (e.g. '茅台', '600519', '阿里巴巴')",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results (default: 10)",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "xueqiu_hot_posts",
                "description": (
                    "Get trending posts from Xueqiu (雪球) community. "
                    "Returns hot posts with title, text snippet, author, "
                    "likes, and URL.\n\n"
                    "Use this when the user wants to:\n"
                    "- See what's trending in the Chinese stock community\n"
                    "- Get market sentiment from Chinese investors\n"
                    "- Find popular investment discussions"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Max posts to return (default: 20, max: 50)",
                            "default": 20,
                        },
                    },
                },
            },
            {
                "name": "xueqiu_hot_stocks",
                "description": (
                    "Get hot stock rankings from Xueqiu (雪球). "
                    "Returns popular or most-watched stocks with price, "
                    "change, and rank.\n\n"
                    "Use this when the user wants to:\n"
                    "- See which stocks are trending in China\n"
                    "- Check market popularity / attention rankings\n"
                    "- Discover hot stocks being discussed"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Max stocks to return (default: 10, max: 50)",
                            "default": 10,
                        },
                        "stock_type": {
                            "type": "integer",
                            "description": "10=人气榜 (popularity, default), 12=关注榜 (attention)",
                            "default": 10,
                        },
                    },
                },
            },
            {
                "name": "xueqiu_watchlist",
                "description": (
                    "Get quotes for all stocks in your Xueqiu watchlist at once. "
                    "Configure stocks in ~/.webmirage/config.yaml under 'xueqiu_watchlist'. "
                    "Returns each stock's price, change, PE, PB, and market cap.\n\n"
                    "Use this when the user wants to:\n"
                    "- Check all portfolio holdings at once\n"
                    "- Monitor a list of stocks for valuation comparison\n"
                    "- '看看我的持仓行情'\n"
                    "- '查看我的自选股'"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

    async def handle_call(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Dispatch a tool call to the appropriate handler."""
        try:
            client = self._get_client()

            if tool_name == "xueqiu_quote":
                return _format_quote(client.get_quote(arguments["symbol"]))

            elif tool_name == "xueqiu_search":
                return _format_search_results(
                    arguments["query"],
                    client.search_stock(
                        query=arguments["query"],
                        limit=arguments.get("limit", 10),
                    ),
                )

            elif tool_name == "xueqiu_hot_posts":
                posts = client.get_hot_posts(
                    limit=arguments.get("limit", 20),
                )
                return _format_posts(posts)

            elif tool_name == "xueqiu_hot_stocks":
                stocks = client.get_hot_stocks(
                    limit=arguments.get("limit", 10),
                    stock_type=arguments.get("stock_type", 10),
                )
                return _format_hot_stocks(stocks)

            elif tool_name == "xueqiu_watchlist":
                config = cfg.get_config()
                watchlist = config.get("xueqiu_watchlist", [])
                if not watchlist:
                    return (
                        "No watchlist configured. Add stocks to "
                        "~/.webmirage/config.yaml:\n"
                        "  xueqiu_watchlist:\n"
                        "    - SH601318\n"
                        "    - 09988\n"
                        "    - 00700\n"
                        "    - AAPL"
                    )
                quotes = []
                for symbol in watchlist:
                    try:
                        quotes.append(client.get_quote(symbol))
                    except Exception as exc:
                        logger.warning("Failed to fetch quote for {}: {}", symbol, exc)
                        quotes.append({"symbol": symbol, "name": "", "error": str(exc)})
                return _format_watchlist(quotes)

            else:
                return "Error: Unknown tool '{}'".format(tool_name)

        except XueqiuError as exc:
            return "Xueqiu API error: {}".format(exc)
        except Exception as exc:
            logger.exception("Unexpected error in tool call")
            return "Error: {}".format(exc)


# ── Formatting helpers ───────────────────────────────────────────────────


def _fmt_num(v: Any, suffix: str = "") -> str:
    """Format a number value, handling None."""
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return "{:.2f}{}".format(v, suffix)
    return "{}{}".format(v, suffix)


def _fmt_pct(v: Any) -> str:
    """Format a percentage value."""
    if v is None:
        return "N/A"
    if isinstance(v, (int, float)):
        sign = "+" if v >= 0 else ""
        return "{}{:.2f}%".format(sign, v)
    return str(v)


def _fmt_market_cap(v: Any) -> str:
    """Format market cap in human-readable units."""
    if v is None:
        return "N/A"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if v >= 1e12:
        return "{:.2f}万亿".format(v / 1e12)
    if v >= 1e8:
        return "{:.2f}亿".format(v / 1e8)
    if v >= 1e4:
        return "{:.2f}万".format(v / 1e4)
    return str(v)


def _fmt_volume(v: Any) -> str:
    """Format volume in human-readable units."""
    if v is None:
        return "N/A"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if v >= 1e8:
        return "{:.2f}亿手".format(v / 1e8)
    if v >= 1e4:
        return "{:.2f}万手".format(v / 1e4)
    return "{}手".format(v)


def _format_quote(q: dict[str, Any]) -> str:
    """Format a single stock quote as readable text."""
    symbol = q.get("symbol", "")
    name = q.get("name", "")
    current = q.get("current")
    percent = q.get("percent")
    chg = q.get("chg")

    if q.get("error"):
        return "Error fetching {}: {}".format(symbol, q["error"])

    if current is None:
        return "No data for {} ({})".format(symbol, name)

    lines = [
        "=" * 50,
        "{} ({})".format(name, symbol) if name else symbol,
        "=" * 50,
        "",
        "价格:  {}  ({})".format(
            _fmt_num(current),
            _fmt_pct(percent),
        ),
    ]

    if chg is not None:
        lines.append("涨跌:  {}".format(_fmt_num(chg)))

    lines.extend([
        "",
        "--- 行情 ---",
        "今开:  {}    昨收:  {}".format(
            _fmt_num(q.get("open")),
            _fmt_num(q.get("last_close")),
        ),
        "最高:  {}    最低:  {}".format(
            _fmt_num(q.get("high")),
            _fmt_num(q.get("low")),
        ),
        "成交量: {}    换手率: {}".format(
            _fmt_volume(q.get("volume")),
            _fmt_num(q.get("turnover_rate"), "%"),
        ),
        "",
        "--- 估值 ---",
        "PE(TTM):  {}    PE(预测):  {}".format(
            _fmt_num(q.get("pe_ttm")),
            _fmt_num(q.get("pe_forecast")),
        ),
        "PB:       {}    EPS:      {}".format(
            _fmt_num(q.get("pb")),
            _fmt_num(q.get("eps")),
        ),
        "总市值:   {}".format(_fmt_market_cap(q.get("market_capital"))),
    ])

    return "\n".join(lines)


def _format_search_results(query: str, results: list[dict[str, Any]]) -> str:
    """Format stock search results."""
    if not results:
        return 'No stocks found for "{}"'.format(query)

    lines = [
        "=" * 50,
        'Search: "{}"'.format(query),
        "Found {} results".format(len(results)),
        "=" * 50,
    ]

    for i, s in enumerate(results, 1):
        lines.append(
            "{}. {} ({}) - {}".format(
                i,
                s.get("symbol", ""),
                s.get("exchange", ""),
                s.get("name", ""),
            )
        )

    return "\n".join(lines)


def _format_posts(posts: list[dict[str, Any]]) -> str:
    """Format hot posts as readable text."""
    if not posts:
        return "No hot posts found."

    lines = [
        "=" * 50,
        "雪球热帖 (Hot Posts)",
        "Found {} posts".format(len(posts)),
        "=" * 50,
    ]

    for i, post in enumerate(posts, 1):
        lines.append("\n--- Post {} ---".format(i))
        title = post.get("title", "")
        if title:
            lines.append("标题: {}".format(title))
        lines.append("作者: {}".format(post.get("author", "")))
        lines.append("点赞: {}".format(post.get("likes", 0)))
        text = post.get("text", "")
        if text:
            lines.append("内容: {}".format(text))
        url = post.get("url", "")
        if url:
            lines.append("链接: {}".format(url))

    return "\n".join(lines)


def _format_hot_stocks(stocks: list[dict[str, Any]]) -> str:
    """Format hot stock rankings as readable text."""
    if not stocks:
        return "No hot stocks found."

    lines = [
        "=" * 50,
        "雪球热门股票 (Hot Stocks)",
        "Found {} stocks".format(len(stocks)),
        "=" * 50,
        "",
        "{:<4} {:<10} {:<10} {:>10} {:>8}".format(
            "排名", "代码", "名称", "现价", "涨跌幅"
        ),
        "-" * 50,
    ]

    for s in stocks:
        lines.append(
            "{:<4} {:<10} {:<10} {:>10} {:>8}".format(
                s.get("rank", ""),
                s.get("symbol", ""),
                s.get("name", "")[:8],
                _fmt_num(s.get("current")),
                _fmt_pct(s.get("percent")),
            )
        )

    return "\n".join(lines)


def _format_watchlist(quotes: list[dict[str, Any]]) -> str:
    """Format watchlist quotes as a comparison table."""
    if not quotes:
        return "No quotes to display."

    lines = [
        "=" * 50,
        "自选股行情 (Watchlist)",
        "{} stocks".format(len(quotes)),
        "=" * 50,
        "",
        "{:<10} {:<8} {:>8} {:>8} {:>8} {:>8} {:>12}".format(
            "代码", "名称", "现价", "涨跌幅", "PE(TTM)", "PB", "总市值"
        ),
        "-" * 70,
    ]

    for q in quotes:
        name = q.get("name", "") or "N/A"
        lines.append(
            "{:<10} {:<8} {:>8} {:>8} {:>8} {:>8} {:>12}".format(
                q.get("symbol", ""),
                name[:6],
                _fmt_num(q.get("current")),
                _fmt_pct(q.get("percent")),
                _fmt_num(q.get("pe_ttm")),
                _fmt_num(q.get("pb")),
                _fmt_market_cap(q.get("market_capital")),
            )
        )

    return "\n".join(lines)
