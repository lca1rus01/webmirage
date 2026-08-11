"""闲鱼商品智能评分系统 v3.0 — 通用 + AI 协作版

设计理念：
  代码做代码擅长的（时效性、合规检查、规格提取、价格定位），
  AI 做 AI 擅长的（跨商品横向对比，综合评估性价比）。

评分维度（总分 100）：
  时效性   (30分) — 代码自动：新鲜度×稀缺度组合矩阵，8天后稀缺方向反转
  基础合规 (10分) — 代码自动：有标题/价格/描述/图片/非垃圾
  性价比   (60分) — AI 评估：scorer 提供结构化规格供 AI 横向对比

使用方式：
    from webmirage.platforms.xianyu.scorer import score_items, format_ranked

    scored = score_items(items)          # items 来自 XianyuClient.search_products()
    print(format_ranked(scored))          # 格式化输出，AI 读完评估性价比
"""

from __future__ import annotations

import re
import statistics
from datetime import datetime
from typing import Any


# ============================================================
# 评分规则配置
# ============================================================

# --- 排除关键词（标题含这些词的商品不参与排名） ---
EXCLUDE_KEYWORDS: list[str] = [
    "组装机", "推土机", "塔式", "回收", "高价回收", "收机",
    "求购", "换购", "模型", "玩具", "贴纸", "贴膜",
]

# --- 时效性矩阵 (满分 30) ---
# 行 = 发布天数区间，列 = 想要人数区间
# 核心设计：8天后稀缺度方向反转（旧+人少=滞销有问题，旧+人多=有真实需求）
#
#           0-3人    4-10人   11-20人   20+人
# 0-1天      30       25       20       15      ← 新+人少=最佳机会
# 2-3天      27       22       17       12
# 4-7天      20       16       12        8
# 8天+       10       12       14       16      ← 反转：旧+人多反而更高

_TIMELINESS_MATRIX: dict[tuple[str, str], int] = {
    ("today", "low"):   30,  ("today", "mid"):   25,  ("today", "high"):   20,  ("today", "vhigh"):   15,
    ("2-3d",  "low"):   27,  ("2-3d",  "mid"):   22,  ("2-3d",  "high"):   17,  ("2-3d",  "vhigh"):   12,
    ("4-7d",  "low"):   20,  ("4-7d",  "mid"):   16,  ("4-7d",  "high"):   12,  ("4-7d",  "vhigh"):    8,
    ("8d+",   "low"):   10,  ("8d+",   "mid"):   12,  ("8d+",   "high"):   14,  ("8d+",   "vhigh"):   16,
}


# ============================================================
# 解析工具函数
# ============================================================

def _parse_price(price_str: str | int | float | None) -> float:
    if price_str is None:
        return 0.0
    if isinstance(price_str, (int, float)):
        return float(price_str)
    matched = re.search(r"[\d.]+", str(price_str))
    return float(matched.group()) if matched else 0.0


def _parse_want_count(want_str: str | int | None) -> int:
    if want_str is None:
        return 0
    if isinstance(want_str, int):
        return want_str
    matched = re.search(r"\d+", str(want_str))
    return int(matched.group()) if matched else 0


def _parse_publish_time(item: dict[str, Any]) -> datetime | None:
    ms = item.get("publish_time_ms") or item.get("publishTime")
    if ms and str(ms).isdigit():
        try:
            return datetime.fromtimestamp(int(ms) / 1000)
        except (ValueError, OSError):
            pass
    pt = item.get("publish_time") or item.get("publishTime")
    if pt:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(pt).strip(), fmt)
            except ValueError:
                continue
    return None


def _calc_days(item: dict[str, Any], now: datetime) -> int:
    pub = _parse_publish_time(item)
    if pub is None:
        return 999
    days = (now - pub).days
    return max(0, days)


# ============================================================
# 时效性评分 (30分)
# ============================================================

def _days_tier(days: int) -> str:
    if days <= 1:
        return "today"
    if days <= 3:
        return "2-3d"
    if days <= 7:
        return "4-7d"
    return "8d+"


def _wants_tier(wants: int) -> str:
    if wants <= 3:
        return "low"
    if wants <= 10:
        return "mid"
    if wants <= 20:
        return "high"
    return "vhigh"


def _score_timeliness(days: int, wants: int) -> tuple[int, str]:
    """组合时效性评分（新鲜度×稀缺度矩阵，满分30）。"""
    d = _days_tier(days)
    w = _wants_tier(wants)
    score = _TIMELINESS_MATRIX[(d, w)]

    if days == 0:
        day_label = "今天"
    elif days == 1:
        day_label = "昨天"
    else:
        day_label = f"{days}天前"

    want_label = f"{wants}人想要" if wants > 0 else "无人想要"
    return score, f"{day_label}, {want_label}"


# ============================================================
# 基础合规评分 (10分)
# ============================================================

def _score_compliance(item: dict[str, Any]) -> tuple[int, str]:
    """基础合规检查（满分10）。"""
    score = 0
    details = []

    # 有标题
    if (item.get("title") or "").strip():
        score += 2
    # 有价格
    if _parse_price(item.get("price")) > 0:
        score += 2
    # 有描述
    if (item.get("desc") or "").strip():
        score += 2
    # 有图片
    if item.get("pic_url") or item.get("pic_urls"):
        score += 2
    # 不含排除关键词（能进来说明已通过过滤，直接给分）
    score += 2

    return score, f"{score}/10"


# ============================================================
# 价格定位（动态，相对中位价）
# ============================================================

def _price_position(price: float, all_prices: list[float]) -> tuple[str, float]:
    """返回价格位置标签和中位价。"""
    valid = [p for p in all_prices if p > 0]
    if not valid or price <= 0:
        return "未知", 0.0

    median = statistics.median(valid)
    if median == 0:
        return "未知", 0.0

    ratio = price / median
    if ratio <= 0.70:
        label = "捡漏"
    elif ratio <= 0.90:
        label = "偏低"
    elif ratio <= 1.10:
        label = "中等"
    elif ratio <= 1.30:
        label = "偏高"
    else:
        label = "高价"

    return label, median


# ============================================================
# 灵活规格提取器
# ============================================================

def extract_specs(title: str, desc: str = "") -> list[str]:
    """从标题和描述中提取规格信息。

    灵活提取——有什么提什么，不同品类的商品自然产出不同的规格。
    返回扁平列表，如 ["芯片=M4", "16G", "256G", "循环=7次", "无拆修", "在保"]
    """
    text = (title + " " + desc).lower()
    specs: list[str] = []
    seen_keys: set[str] = set()

    def add(spec: str) -> None:
        """添加规格，按 = 前的去重。"""
        key = spec.split("=")[0] if "=" in spec else spec
        if key not in seen_keys:
            specs.append(spec)
            seen_keys.add(key)

    # ── 芯片 / CPU ──────────────────────────────
    _extract_chip(text, add)

    # ── 内存 + 存储（从 X+Y 格式提取）──────────────
    _extract_ram_storage(text, add)

    # ── 成色（按精确度排序，先匹配更具体的）──────────
    if re.search(r"9\.?9成新|99新|几乎全新|充新", text):
        add("成色=99新")
    elif re.search(r"9\.0成新|9成新", text):
        add("成色=9成新")
    elif re.search(r"8\.?5成新|85新|8成新|8\.0成新", text):
        add("成色=8成新")
    elif re.search(r"(?<!几乎)全新|未拆封|未激活|sealed", text):
        # "几乎全新"不含"全新"——用 lookbehind 排除
        add("成色=全新")

    # ── 使用痕迹 ──────────────────────────────────
    m = re.search(r"循环(\d+)\s*次?", text)
    if m:
        add(f"循环={m.group(1)}次")

    m = re.search(r"快门(\d+)\s*次?", text)
    if m:
        add(f"快门={m.group(1)}次")

    m = re.search(r"(\d+\.?\d?)\s*万?公里", text)
    if m and "公里" in text:
        add(f"里程={m.group(1)}万公里")

    # ── 电池 ──────────────────────────────────────
    m = re.search(r"电池.*?(\d{2,3})\s*%", text)
    if m:
        add(f"电池={m.group(1)}%")
    else:
        m = re.search(r"健康度.*?(\d{2,3})\s*%", text)
        if m:
            add(f"电池={m.group(1)}%")

    # ── 完整性（互斥：无拆修/有拆修 二选一，无划痕/有划痕 二选一）──
    if re.search(r"无拆无修|无拆修", text):
        add("无拆修")
    elif re.search(r"拆机|拆修|维修过|修过", text):
        add("有拆修")

    if re.search(r"无划痕|无磕碰", text):
        add("无划痕")
    elif re.search(r"有划痕|划伤|刮痕|磕碰|掉漆|磨损明显", text):
        add("有划痕")

    if re.search(r"不开机|黑屏|花屏|无法开机", text):
        add("功能故障")

    # ── 保修 ──────────────────────────────────────
    if re.search(r"在保|保修|质保|apple\s?care|ac\+", text):
        add("在保")

    # ── 尺寸 ──────────────────────────────────────
    m = re.search(r"(\d+\.?\d?)\s*(?:寸|英寸|inch)", text)
    if m:
        add(f"尺寸={m.group(1)}寸")

    # ── 颜色 ──────────────────────────────────────
    for kw in ["午夜色", "星光色", "天蓝色", "深空灰", "银色", "蓝色",
               "黑色", "白色", "灰色", "金色", "玫瑰金", "紫色", "绿色", "粉色"]:
        if kw in text:
            add(f"颜色={kw}")
            break

    # ── 配件 ──────────────────────────────────────
    for pat, label in [
        (r"原装盒|原包装|原盒", "原装盒"),
        (r"原装.*?(?:充电器|电源)|充电器.*?原装", "原装充电器"),
        (r"全套|配件齐全", "配件齐全"),
    ]:
        if re.search(pat, text):
            add(label)

    # ── 版本 ──────────────────────────────────────
    for kw in ["国行", "港版", "港行", "日版", "美版", "韩版"]:
        if kw in text:
            add("港版" if kw in ("港版", "港行") else kw)
            break

    # ── 发票 ──────────────────────────────────────
    if re.search(r"发票|购买凭证|电子凭证", text):
        add("有发票")

    # ── 屏幕相关（显示器/笔记本）──────────────────
    if re.search(r"oled", text):
        add("OLED屏")
    m = re.search(r"(\d{2,3})\s*hz", text)
    if m:
        add(f"刷新率={m.group(1)}Hz")
    if re.search(r"\b4k\b|2160p", text):
        add("4K")

    # ── 型号关键词（手机/主机/相机等）──────────────
    m = re.search(r"(?:iphone|ipad)\s*(\d{1,2}\s?(?:pro|plus|max|mini)?)", text)
    if m:
        add(f"型号=iPhone {m.group(1)}".strip())

    for kw in ["switch oled", "switch lite", "switch", "ps5", "ps4", "xbox"]:
        if kw in text:
            add(f"型号={kw}")
            break

    for kw in ["apple watch", "galaxy watch", "garmin", "华为手表"]:
        if kw in text:
            add(f"型号={kw}")
            break

    return specs


def _extract_chip(text: str, add) -> None:
    """提取芯片信息。"""
    # Apple Silicon
    for pat, label in [
        (r"m4[\s-]?max", "芯片=M4 Max"),
        (r"m4[\s-]?pro", "芯片=M4 Pro"),
        (r"\bm4\b", "芯片=M4"),
        (r"m3[\s-]?max", "芯片=M3 Max"),
        (r"m3[\s-]?pro", "芯片=M3 Pro"),
        (r"\bm3\b", "芯片=M3"),
        (r"m2[\s-]?pro", "芯片=M2 Pro"),
        (r"\bm2\b", "芯片=M2"),
        (r"m1[\s-]?pro", "芯片=M1 Pro"),
        (r"\bm1\b", "芯片=M1"),
    ]:
        if re.search(pat, text):
            add(label)
            return

    # Intel (capture full model)
    m = re.search(r"(i[3579])[-\s]?(\d{4,5})", text)
    if m:
        add(f"芯片={m.group(1).upper()}-{m.group(2)}")
        return

    # AMD Ryzen
    m = re.search(r"(r[579])[-\s]?(\d{4})", text)
    if m:
        add(f"芯片={m.group(1).upper()}-{m.group(2)}")
        return

    # Snapdragon / 骁龙
    if re.search(r"snapdragon|骁龙", text):
        m = re.search(r"(?:骁龙|snapdragon)\s*8\s?gen\s?([234])", text)
        if m:
            add(f"芯片=骁龙8Gen{m.group(1)}")
        else:
            add("芯片=骁龙")
        return

    # Low-power Intel
    for pat, label in [
        (r"n5095", "芯片=N5095"), (r"n5105", "芯片=N5105"),
        (r"n100", "芯片=N100"), (r"j4125", "芯片=J4125"),
    ]:
        if re.search(pat, text):
            add(label)
            return


def _extract_ram_storage(text: str, add) -> None:
    """提取内存和存储信息。"""
    # X+Y 格式 (如 "16+256", "8+128")
    m = re.search(r"(\d+)\s*\+\s*(\d+)", text)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a <= 64 and 64 <= b <= 8192:
            add(f"内存={a}G")
            add(f"存储={b}G")
            return
        if b <= 64 and 64 <= a <= 8192:
            add(f"内存={b}G")
            add(f"存储={a}G")
            return

    # 内存 standalone
    m = re.search(r"(\d+)\s*g(?:b)?\s*(?:内存|mem|ddr|ram|lpddr)", text)
    if m:
        add(f"内存={m.group(1)}G")
    else:
        m = re.search(r"(\d+)\s*g(?:b)?(?=\s*(?:，|,|\+|/| ddr| lpddr))", text)
        if m and int(m.group(1)) <= 64:
            add(f"内存={m.group(1)}G")

    # 存储 standalone
    m = re.search(r"(\d+)\s*(g|t)b?\s*(?:固态|ssd|硬盘|存储|rom|闪存|nvme|m\.2)", text)
    if m:
        unit = "G" if m.group(2) == "g" else "T"
        add(f"存储={m.group(1)}{unit}")
    else:
        m = re.search(r"(\d+)\s*g(?:b)?(?=\s*(?:，|,|。|原|国|含|带))", text)
        if m and int(m.group(1)) >= 64:
            add(f"存储={m.group(1)}G")

    # Fallback: 两个空格分隔的 "数字G" → 第一个=内存，第二个=存储
    # 仅当上面都没匹配到时触发（add 会自动去重）
    all_g = re.findall(r"(\d+)\s*g(?:b)?\b", text)
    if len(all_g) >= 2:
        vals = [int(x) for x in all_g if int(x) > 0]
        ram_val = next((v for v in vals if 2 <= v <= 64), None)
        storage_vals = [v for v in vals if v >= 64 and v != ram_val]
        if ram_val:
            add(f"内存={ram_val}G")
        if storage_vals:
            add(f"存储={storage_vals[0]}G")


# ============================================================
# 排除过滤
# ============================================================

def _passes_filter(item: dict[str, Any]) -> bool:
    """通用排除过滤。"""
    text = ((item.get("title") or "") + " " + (item.get("desc") or "")).lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw in text:
            return False
    return True


# ============================================================
# 核心评分函数
# ============================================================

def score_items(
    items: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """对搜索结果列表评分并按自动分（时效性+合规）降序排名。

    性价比(60分)不自动评分，留给 AI 结合提取信息横向评估。

    Returns:
        按自动分降序排列的商品列表，每项增加：
        _timeliness, _compliance, _auto_score, _specs, _price_pos, _median
    """
    if now is None:
        now = datetime.now()

    # 过滤
    filtered = [item for item in items if _passes_filter(item)]

    # 提取所有价格用于动态价格定位
    all_prices = [_parse_price(item.get("price")) for item in filtered]
    median = statistics.median([p for p in all_prices if p > 0]) if all_prices else 0

    scored: list[dict[str, Any]] = []
    for item in filtered:
        days = _calc_days(item, now)
        wants = _parse_want_count(item.get("want_count"))

        t_score, t_label = _score_timeliness(days, wants)
        c_score, c_label = _score_compliance(item)
        p_pos, _ = _price_position(_parse_price(item.get("price")), all_prices)
        specs = extract_specs(item.get("title") or "", item.get("desc") or "")

        auto_score = t_score + c_score

        scored.append({
            **item,
            "_timeliness": (t_score, t_label),
            "_compliance": (c_score, c_label),
            "_auto_score": auto_score,
            "_specs": specs,
            "_price_pos": p_pos,
            "_median": median,
        })

    scored.sort(key=lambda x: x.get("_auto_score", 0), reverse=True)
    return scored


# ============================================================
# 格式化输出
# ============================================================

def _tier_label(score: int) -> str:
    """自动分梯队（满分40）。"""
    if score >= 38:
        return "★ 强烈关注"
    if score >= 32:
        return "☆ 值得关注"
    if score >= 25:
        return "可看"
    if score >= 15:
        return "一般"
    return "观望"


def format_ranked(
    scored_items: list[dict[str, Any]],
    keyword: str = "",
    top_n: int = 0,
) -> str:
    """格式化评分结果为文本。

    输出包含：自动评分(时效性+合规) + 灵活规格提取 + 价格位置。
    性价比(60分)由 AI 读取后横向评估，不自动打分。
    """
    if not scored_items:
        header = "闲鱼评分: 无合格商品"
        if keyword:
            header += f' (关键词: "{keyword}")'
        return header + "\n\n可能原因：所有商品均被排除关键词过滤，或搜索结果为空。"

    items = scored_items[:top_n] if top_n > 0 else scored_items
    median = items[0].get("_median", 0) if items else 0

    lines = [
        "=" * 60,
        f'闲鱼智能评分 v3.0 (关键词: "{keyword}")' if keyword else "闲鱼智能评分 v3.0",
        "时效性30 + 合规10 = 自动分40 | 性价比60(AI评估) = 满分100",
        f"共 {len(items)} 件商品 (原始 {len(scored_items)} 件)",
    ]
    if median > 0:
        lines.append(f"中位价: ¥{int(median)}")
    lines.append("=" * 60)

    for i, item in enumerate(items, 1):
        t = item.get("_timeliness", (0, ""))
        c = item.get("_compliance", (0, ""))
        auto = item.get("_auto_score", 0)
        specs = item.get("_specs", [])
        price_pos = item.get("_price_pos", "未知")
        price = _parse_price(item.get("price"))
        url = item.get("url") or item.get("link") or ""
        title = (item.get("title") or "（无标题）")[:50]
        tier = _tier_label(auto)

        specs_str = " | ".join(specs) if specs else "（未提取到规格）"

        lines.append("")
        lines.append(f"--- #{i} | 自动分 {auto}/40 | {tier} ---")
        lines.append(f"标题: {title}")
        lines.append(f"价格: ¥{int(price)}  [价格位置: {price_pos}]")
        lines.append(
            f"时效: {t[0]}/30 ({t[1]}) + 合规: {c[0]}/10 = {auto}/40"
        )
        lines.append(f"提取: {specs_str}")

        want = _parse_want_count(item.get("want_count"))
        if item.get("publish_time"):
            lines.append(f"发布: {item['publish_time']}")
        if want:
            lines.append(f"想要: {want}人")
        if item.get("area"):
            lines.append(f"地区: {item['area']}")
        if item.get("seller_nick"):
            lines.append(f"卖家: {item['seller_nick']}")
        if url:
            lines.append(f"链接: {url}")
        lines.append(f"商品ID: {item.get('item_id', '')}")

    lines.append("")
    lines.append("=" * 60)
    lines.append("↑ 以上时效性+合规分为代码自动评分")
    lines.append("  性价比(60分)请结合「提取」信息横向对比评估")
    lines.append("  提示: 使用 xianyu_get_item_detail 查看某商品完整详情")

    return "\n".join(lines)
