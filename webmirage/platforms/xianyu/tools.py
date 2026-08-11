"""MCP tool definitions for the Xianyu (闲鱼/Goofish) platform.

暴露给 AI 的 MCP 工具：

    - xianyu_search_products : 搜索闲鱼商品（高级版，支持价格区间/个人卖家/排序）
    - xianyu_score_search    : 搜索+智能评分v3.0（时效30+合规10自动 / 性价比60留给AI评估）
    - xianyu_get_item_detail: 获取单个商品详情（含描述/卖家/图片列表）
    - xianyu_get_items       : 获取自己账号的在售商品列表
    - xianyu_confirm_delivery : 确认订单虚拟发货

搜索结果返回丰富的商品信息（价格、想要数、标签、卖家、上新时间等），
供 AI 做综合评价（如对比不同配置的价格性价比）。
"""

from __future__ import annotations

import logging
from typing import Any

from loguru import logger

from ..base import PlatformTools
from ... import config as cfg
from .client import XianyuClient, XianyuError
from .scorer import score_items, format_ranked

logger = logging.getLogger(__name__)


class XianyuTools(PlatformTools):
    """闲鱼/Goofish 平台工具集。"""

    name = "xianyu"
    description = "闲鱼(Goofish)商品搜索、商品详情、我的商品列表、确认订单发货"

    def __init__(self) -> None:
        self._client: XianyuClient | None = None

    def is_available(self) -> bool:
        """闲鱼接口需要完整 cookie（含 _m_h5_tk 与 unb）。"""
        c = cfg.get_config()
        cookie = c.get("xianyu_cookie", "")
        return bool(cookie and "_m_h5_tk" in cookie and "unb" in cookie)

    def _get_client(self) -> XianyuClient:
        if self._client is None:
            c = cfg.get_config()
            self._client = XianyuClient(
                cookie_str=c.get("xianyu_cookie", ""),
                user_id=c.get("xianyu_user_id", ""),
            )
        return self._client

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            # ── 搜索商品（高级版） ──────────────────────────────────────
            {
                "name": "xianyu_search_products",
                "description": (
                    "搜索闲鱼(Goofish)商品。支持价格区间、个人卖家过滤、上新天数、"
                    "排序等高级筛选。返回每个商品的标题、价格、地区、卖家、想要数、"
                    "标签、发布时间、链接等丰富信息。\n\n"
                    "Use this when the user wants to:\n"
                    "- 搜闲鱼上的某个商品 / 看看别人在卖什么\n"
                    "- 调研某类二手商品的价格区间\n"
                    "- 找特定关键词的商品（如 '16G内存小主机'）\n"
                    "- 过滤个人卖家闲置（排除专业商家）\n"
                    "- 按价格/上新时间排序筛选\n\n"
                    "返回的数据适合 AI 做综合评价：对比不同配置的价格、"
                    "判断性价比、识别异常低价等。"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "搜索关键词，如 'iPhone 15'、'机械键盘'、'16G小主机'",
                        },
                        "page": {
                            "type": "integer",
                            "description": "页码，从 1 开始（默认 1）",
                            "default": 1,
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "每页数量（默认 30，最大 50）",
                            "default": 30,
                        },
                        "price_min": {
                            "type": "number",
                            "description": "最低价格（可选），如 100",
                        },
                        "price_max": {
                            "type": "number",
                            "description": "最高价格（可选），如 5000",
                        },
                        "personal_only": {
                            "type": "boolean",
                            "description": "是否只看个人卖家闲置（排除专业商家），默认 true",
                            "default": True,
                        },
                        "publish_days": {
                            "type": "integer",
                            "description": "只看 N 天内新上架的商品（可选），如 7=最近一周",
                        },
                        "sort_field": {
                            "type": "string",
                            "description": "排序字段：sort_time=按上新时间(默认), sort_price=按价格",
                            "default": "",
                        },
                        "sort_value": {
                            "type": "string",
                            "description": "排序值：pubTime=上新时间, price=价格。配合 sort_field 使用",
                            "default": "",
                        },
                    },
                    "required": ["keyword"],
                },
            },
            # ── 搜索+智能评分排名 ────────────────────────────────────
            {
                "name": "xianyu_score_search",
                "description": (
                    "搜索闲鱼商品并智能评分。通用评分系统 v3.0，适用于任何品类。\n"
                    "评分维度：\n"
                    "时效性(30分): 新鲜度×稀缺度组合矩阵，8天后稀缺方向反转\n"
                    "  - 新+人少=高分(机会)，旧+人少=低分(滞销)，旧+人多=中分(有需求)\n"
                    "合规(10分): 有标题/价格/描述/图片/非垃圾\n"
                    "性价比(60分): 不自动评分，由AI结合提取信息横向对比评估\n\n"
                    "scorer 会从标题/描述中灵活提取规格(芯片/内存/存储/成色/循环/保修等)，\n"
                    "不同品类自然产出不同规格，输出供AI横向对比。\n"
                    "价格位置基于动态中位价，自适应任意价格区间。\n\n"
                    "Use this when the user wants to:\n"
                    "- 搜索并排名二手商品\n"
                    "- 找最新上架且还没被抢的好货\n"
                    "- 对比多个商品的综合性价比\n\n"
                    "参数同 xianyu_search_products，额外支持 top_n 限制返回数量。"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "搜索关键词，如 '16G迷你主机'",
                        },
                        "page": {
                            "type": "integer",
                            "default": 1,
                        },
                        "page_size": {
                            "type": "integer",
                            "default": 30,
                        },
                        "price_min": {"type": "number"},
                        "price_max": {"type": "number"},
                        "personal_only": {
                            "type": "boolean",
                            "default": True,
                        },
                        "publish_days": {"type": "integer"},
                        "sort_field": {"type": "string", "default": ""},
                        "sort_value": {"type": "string", "default": ""},
                        "top_n": {
                            "type": "integer",
                            "description": "只返回前N名（0=全部，默认15）",
                            "default": 15,
                        },
                    },
                    "required": ["keyword"],
                },
            },
            # ── 商品详情 ──────────────────────────────────────────────
            {
                "name": "xianyu_get_item_detail",
                "description": (
                    "获取闲鱼单个商品详情。返回商品标题、价格、地区、描述、"
                    "卖家信息、图片列表等完整详情数据。\n\n"
                    "Use this when the user wants to:\n"
                    "- 查看某个商品的详细描述和规格\n"
                    "- 获取卖家信息（卖家ID、昵称、头像）\n"
                    "- 查看商品的所有图片\n"
                    "- 对搜索结果中的某个商品做深入了解后再决定是否购买\n\n"
                    "配合 xianyu_search_products 使用：先搜索得到 item_id，"
                    "再调详情获取完整信息做综合评价。"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "item_id": {
                            "type": "string",
                            "description": "闲鱼商品 ID（从搜索结果中获取）",
                        },
                    },
                    "required": ["item_id"],
                },
            },
            # ── 我的商品列表 ──────────────────────────────────────────
            {
                "name": "xianyu_get_items",
                "description": (
                    "获取你自己闲鱼账号的在售商品列表。返回每个商品的 ID、"
                    "标题、价格、状态、链接。\n\n"
                    "Use this when the user wants to:\n"
                    "- 看看我闲鱼上挂了哪些东西\n"
                    "- 查自己某个商品的商品 ID（用于发货等操作）\n"
                    "- 检查商品在售状态"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "page": {
                            "type": "integer",
                            "description": "页码，从 1 开始（默认 1）",
                            "default": 1,
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "每页数量（默认 20，最大 50）",
                            "default": 20,
                        },
                    },
                },
            },
            # ── 确认发货 ──────────────────────────────────────────────
            {
                "name": "xianyu_confirm_delivery",
                "description": (
                    "确认闲鱼订单虚拟发货（虚拟商品无需物流单号即可发货）。\n\n"
                    "Use this when the user wants to:\n"
                    "- 给某个闲鱼订单点击发货\n"
                    "- 买家付款后自动/手动确认发货\n\n"
                    "注意：这是虚拟发货(consign dummy)，适用于虚拟商品；"
                    "实物发货需走物流接口，不在本工具范围。"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "order_id": {
                            "type": "string",
                            "description": "闲鱼订单 ID（数字字符串）",
                        },
                    },
                    "required": ["order_id"],
                },
            },
        ]

    async def handle_call(self, tool_name: str, arguments: dict[str, Any]) -> str:
        import asyncio

        try:
            client = self._get_client()

            if tool_name == "xianyu_search_products":
                items = await asyncio.to_thread(
                    client.search_products,
                    arguments["keyword"],
                    arguments.get("page", 1),
                    arguments.get("page_size", 30),
                    # 关键字参数
                    price_min=arguments.get("price_min"),
                    price_max=arguments.get("price_max"),
                    publish_days=arguments.get("publish_days"),
                    personal_only=arguments.get("personal_only", True),
                    sort_field=arguments.get("sort_field", ""),
                    sort_value=arguments.get("sort_value", ""),
                )
                return _format_search(arguments["keyword"], items, arguments)

            elif tool_name == "xianyu_score_search":
                # 搜索 + 智能评分排名
                items = await asyncio.to_thread(
                    client.search_products,
                    arguments["keyword"],
                    arguments.get("page", 1),
                    arguments.get("page_size", 30),
                    price_min=arguments.get("price_min"),
                    price_max=arguments.get("price_max"),
                    publish_days=arguments.get("publish_days"),
                    personal_only=arguments.get("personal_only", True),
                    sort_field=arguments.get("sort_field", ""),
                    sort_value=arguments.get("sort_value", ""),
                )
                scored = score_items(items)
                return format_ranked(
                    scored,
                    keyword=arguments["keyword"],
                    top_n=arguments.get("top_n", 15),
                )

            elif tool_name == "xianyu_get_item_detail":
                result = await asyncio.to_thread(
                    client.get_item_detail,
                    arguments["item_id"],
                )
                return _format_detail(result)

            elif tool_name == "xianyu_get_items":
                items = await asyncio.to_thread(
                    client.get_items,
                    arguments.get("page", 1),
                    arguments.get("page_size", 20),
                )
                return _format_items(items)

            elif tool_name == "xianyu_confirm_delivery":
                result = await asyncio.to_thread(
                    client.confirm_delivery,
                    arguments["order_id"],
                )
                return _format_delivery(result)

            else:
                return "Error: Unknown tool '{}'".format(tool_name)

        except XianyuError as exc:
            return "闲鱼接口错误: {}".format(exc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error in xianyu tool call")
            return "Error: {}".format(exc)


# ── Formatting helpers ────────────────────────────────────────────────────


def _format_search(
    keyword: str,
    items: list[dict[str, Any]],
    args: dict[str, Any] | None = None,
) -> str:
    if not items:
        hint = ""
        if args and (args.get("price_min") or args.get("price_max")):
            hint += f"（价格区间: {args.get('price_min', '不限')}~{args.get('price_max', '不限')}）"
        if args and args.get("publish_days"):
            hint += f"（仅最近 {args['publish_days']} 天上新）"
        return (
            '闲鱼搜索 "{}" 未返回结果。{}\n\n'
            "可能原因：1) 关键词太宽泛/太冷门  2) 价格区间过窄  "
            "3) 纯 HTTP 直调被风控/滑块拦截\n"
            "建议：放宽筛选条件，或在浏览器登录闲鱼后更新 "
            "~/.webmirage/config.yaml 的 xianyu_cookie"
        ).format(keyword, hint)

    # 收集筛选信息
    filters = []
    if args:
        if args.get("personal_only", True):
            filters.append("个人卖家")
        if args.get("price_min") or args.get("price_max"):
            filters.append(
                "价格 {}-{}".format(
                    args.get("price_min", "不限"),
                    args.get("price_max", "不限"),
                )
            )
        if args.get("publish_days"):
            filters.append("近 {} 天上新".format(args["publish_days"]))
        if args.get("sort_field"):
            sort_map = {
                "sort_time": "上新时间",
                "sort_price": "价格",
            }
            filters.append("排序: {}".format(sort_map.get(args["sort_field"], args["sort_field"])))
    filter_text = " | ".join(filters) if filters else "无筛选"

    lines = [
        "=" * 60,
        '闲鱼搜索: "{}"'.format(keyword),
        "筛选: {} | 找到 {} 件商品".format(filter_text, len(items)),
        "=" * 60,
    ]

    for i, it in enumerate(items, 1):
        lines.append("\n--- #{} ---".format(i))
        lines.append("标题: {}".format(it.get("title", "") or "（无标题）"))

        if it.get("price"):
            lines.append("价格: ¥{}".format(it["price"]))

        if it.get("want_count"):
            lines.append("想要: {}人想要".format(it["want_count"]))

        if it.get("tags"):
            lines.append("标签: {}".format(it["tags"]))

        if it.get("area"):
            lines.append("地区: {}".format(it["area"]))

        if it.get("seller_nick"):
            lines.append("卖家: {}".format(it["seller_nick"]))
        if it.get("seller_user_id"):
            lines.append("卖家ID: {}".format(it["seller_user_id"]))

        if it.get("publish_time"):
            lines.append("发布: {}".format(it["publish_time"]))

        if it.get("url"):
            lines.append("链接: {}".format(it["url"]))

        if it.get("pic_url"):
            lines.append("图片: {}".format(it["pic_url"]))

        lines.append("商品ID: {}".format(it.get("item_id", "")))

    lines.append("\n" + "=" * 60)
    lines.append("提示: 使用 xianyu_get_item_detail 工具可查看某个商品的完整详情")
    return "\n".join(lines)


def _format_detail(result: dict[str, Any]) -> str:
    if not result.get("success"):
        return "❌ 商品 {} 详情获取失败: {}".format(
            result.get("item_id", ""), result.get("error", "未知错误")
        )

    d = result
    lines = [
        "=" * 60,
        "闲鱼商品详情",
        "=" * 60,
        "",
        "商品ID: {}".format(d.get("item_id", "")),
        "标题: {}".format(d.get("title", "") or "（无标题）"),
    ]

    if d.get("price"):
        lines.append("价格: ¥{}".format(d["price"]))
    if d.get("area"):
        lines.append("地区: {}".format(d["area"]))

    if d.get("seller_nick"):
        lines.append("")
        lines.append("--- 卖家信息 ---")
        lines.append("昵称: {}".format(d["seller_nick"]))
    if d.get("seller_user_id"):
        lines.append("ID: {}".format(d["seller_user_id"]))
    if d.get("seller_avatar"):
        lines.append("头像: {}".format(d["seller_avatar"]))

    if d.get("desc"):
        lines.append("")
        lines.append("--- 商品描述 ---")
        lines.append(d["desc"])

    if d.get("pic_urls"):
        lines.append("")
        lines.append("--- 图片列表 ({}张) ---".format(len(d["pic_urls"])))
        for i, url in enumerate(d["pic_urls"], 1):
            lines.append("  {}. {}".format(i, url))

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def _format_items(items: list[dict[str, Any]]) -> str:
    if not items:
        return "你的闲鱼账号下没有在售商品。"

    lines = [
        "=" * 50,
        "我的闲鱼在售商品 (My Items)",
        "Found {} items".format(len(items)),
        "=" * 50,
        "",
        "{:<4} {:<14} {:<30} {:<10} {:<8}".format(
            "#", "商品ID", "标题", "价格", "状态"
        ),
        "-" * 70,
    ]
    for i, it in enumerate(items, 1):
        status = "在售" if it.get("status", 0) == 0 else "状态{}".format(it.get("status"))
        lines.append(
            "{:<4} {:<14} {:<30} {:<10} {:<8}".format(
                i,
                str(it.get("id", ""))[:14],
                (it.get("title", "") or "（无标题）")[:30],
                (it.get("price_text") or it.get("price") or "")[:10],
                status,
            )
        )
    return "\n".join(lines)


def _format_delivery(result: dict[str, Any]) -> str:
    if result.get("success"):
        return "✅ 订单 {} 虚拟发货成功".format(result.get("order_id", ""))
    return "❌ 订单 {} 发货失败: {}".format(
        result.get("order_id", ""), result.get("error", "未知错误")
    )
