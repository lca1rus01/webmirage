"""Xianyu (闲鱼/Goofish) API client.

参考 laozuzhen/xianyu-openclaw-channel 项目里对接闲鱼平台的接口方式：
通过 cookie 认证 + mtop H5 API 签名，直接 HTTP 调用闲鱼的 mtop 接口，
无需 Playwright / Node.js / WebSocket 长连接。

mtop 签名机制（来自 xianyu 项目的 generate_sign）：
    app_key = "34839810"
    token   = cookie 中 _m_h5_tk 取 "_" 之前的部分
    sign    = md5("{token}&{t}&{app_key}&{data}")
    其中 t 是毫秒时间戳，data 是请求体 JSON 字符串。

请求方式（参考 secure_confirm_decrypted.py / XianyuAutoAsync.get_item_list_info）：
    POST https://h5api.m.goofish.com/h5/{api}/{version}/
    params  = {jsv, appKey, t, sign, v, type, accountSite, dataType, ...}
    data    = {"data": <json str>}
    Cookie  = 完整 cookie 字符串
    成功判定：ret[0] == "SUCCESS::调用成功"
    token 失效（FAIL_SYS_TOKEN_EXOIRED）则重试

暴露的能力：
    - 商品搜索（mtop.taobao.idlemtopsearch.pc.search）— 支持价格区间、个人卖家过滤、排序、上新天数
    - 商品详情（mtop.taobao.idle.pc.detail）— 含卖家信息、商品描述
    - 商品列表（mtop.idle.web.xyh.item.list）— 自己账号的在售商品
    - 确认发货（mtop.taobao.idle.logistic.consign.dummy）

Cookie 必须包含：
    unb      — 闲鱼/淘宝用户 ID（用于商品列表等接口的 userId）
    _m_h5_tk — mtop 签名 token（形如 "abc123_1716000000000"）
    cookie2 / sgcookie / t / _tb_token_ 等会话凭证
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Optional

from loguru import logger

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_REFERER = "https://www.goofish.com/"
_TIMEOUT = 20
_H5API = "https://h5api.m.goofish.com/h5"
_APP_KEY = "34839810"


class XianyuError(Exception):
    """闲鱼 API 调用错误。"""


def trans_cookies(cookie_str: str) -> dict[str, str]:
    """把 "k1=v1; k2=v2" 形式的 cookie 字符串解析成字典。"""
    cookies: dict[str, str] = {}
    if not cookie_str:
        return cookies
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if "=" in pair:
            name, _, value = pair.partition("=")
            cookies[name.strip()] = value.strip()
    return cookies


def _extract_token(cookies: dict[str, str]) -> str:
    """从 cookie 字典取 mtop 签名 token（_m_h5_tk 的 "_" 前部分）。"""
    raw = cookies.get("_m_h5_tk", "")
    if not raw:
        return ""
    # _m_h5_tk 形如 "abc123_1716000000000"，签名只用前半段
    return raw.split("_", 1)[0]


def _generate_sign(t: str, token: str, data: str) -> str:
    """生成 mtop 签名：md5(token & t & appKey & data)。

    与 xianyu 项目的 generate_sign 完全一致，保证服务端验签通过。
    """
    msg = "{}&{}&{}&{}".format(token, t, _APP_KEY, data)
    return hashlib.md5(msg.encode("utf-8")).hexdigest()


class XianyuClient:
    """闲鱼 mtop H5 API 客户端（cookie 认证 + 签名）。"""

    def __init__(self, cookie_str: str = "", user_id: str = "") -> None:
        self._cookie_str = cookie_str
        self._cookies: dict[str, str] = trans_cookies(cookie_str)
        # 卖家 user_id：优先用传入值，否则从 cookie 的 unb 字段解析
        self._user_id = str(user_id or self._cookies.get("unb", ""))

    @property
    def cookie_str(self) -> str:
        return self._cookie_str

    @property
    def user_id(self) -> str:
        return self._user_id

    def is_configured(self) -> bool:
        """是否具备调 mtop 接口的最低条件：有 _m_h5_tk 与 unb。"""
        return bool(self._cookies.get("_m_h5_tk") and self._user_id)

    # ------------------------------------------------------------------ #
    # 内部：mtop 通用请求
    # ------------------------------------------------------------------ #

    def _build_cookie_header(self) -> str:
        """用当前 cookies 字典重建 Cookie 请求头。"""
        return "; ".join("{}={}".format(k, v) for k, v in self._cookies.items())

    def _update_cookies_from_response(self, resp_headers) -> None:
        """从响应的 set-cookie 头更新内部 cookie，并刷新 cookie 字符串。

        mtop 接口会在 set-cookie 里回写新的 _m_h5_tk / 等会话凭证，
        必须持续更新，否则下一次请求会因 token 不匹配而失败。
        """
        # get_all / get: urllib 的 HTTPMessage 兼容两种取法
        set_cookies = resp_headers.get_all("Set-Cookie") or []
        if not set_cookies:
            return
        changed = False
        for raw in set_cookies:
            head = raw.split(";", 1)[0]
            if "=" not in head:
                continue
            name, _, value = head.partition("=")
            name, value = name.strip(), value.strip()
            if name and self._cookies.get(name) != value:
                self._cookies[name] = value
                changed = True
        if changed:
            self._cookie_str = "; ".join(
                "{}={}".format(k, v) for k, v in self._cookies.items()
            )

    def _mtop_request(
        self,
        api: str,
        version: str,
        data: dict[str, Any],
        extra_params: dict[str, str] | None = None,
        retry_on_token: bool = True,
    ) -> dict[str, Any]:
        """发起一次 mtop POST 请求并返回解析后的 JSON。

        自动签名、自动携带 cookie、自动吸收 set-cookie、token 失效重试一次。
        """
        if not self.is_configured():
            raise XianyuError(
                "闲鱼 cookie 未配置完整：需要 _m_h5_tk 与 unb(user_id)。"
                "请在 ~/.webmirage/config.yaml 配置 xianyu_cookie 与 xianyu_user_id。"
            )

        t = str(int(time.time() * 1000))
        token = _extract_token(self._cookies)
        data_val = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        sign = _generate_sign(t, token, data_val)

        params: dict[str, str] = {
            "jsv": "2.7.2",
            "appKey": _APP_KEY,
            "t": t,
            "sign": sign,
            "v": version,
            "type": "originaljson",
            "accountSite": "xianyu",
            "dataType": "json",
            "timeout": "20000",
            "api": api,
            "sessionOption": "AutoLoginOnly",
        }
        if extra_params:
            params.update(extra_params)

        query_string = urllib.parse.urlencode(params)
        url = "{}/{}/{}/?{}".format(_H5API, api, version, query_string)
        body = urllib.parse.urlencode({"data": data_val}).encode("utf-8")

        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("User-Agent", _UA)
        req.add_header("Referer", _REFERER)
        req.add_header("Origin", "https://www.goofish.com")
        req.add_header("Cookie", self._build_cookie_header())
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("Accept", "application/json")
        req.add_header("Accept-Language", "zh-CN,zh;q=0.9")

        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                self._update_cookies_from_response(resp.headers)
                payload = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise XianyuError("闲鱼接口 HTTP {}: {}".format(exc.code, exc.reason)) from exc
        except Exception as exc:  # noqa: BLE001
            raise XianyuError("网络请求失败: {}".format(exc)) from exc

        try:
            parsed = json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            raise XianyuError("闲鱼接口返回非 JSON: {}...".format(payload[:200]))

        ret = parsed.get("ret") or []
        ret_msg = ret[0] if ret else ""

        # token 失效：刷新 token（set-cookie 已吸收新 _m_h5_tk）后重试一次
        if retry_on_token and "FAIL_SYS_TOKEN" in str(ret_msg).upper():
            logger.warning("mtop token 失效({})，刷新后重试一次", ret_msg)
            return self._mtop_request(
                api, version, data, extra_params, retry_on_token=False
            )

        if ret_msg and not ret_msg.startswith("SUCCESS"):
            raise XianyuError("闲鱼接口返回错误: {}".format(ret_msg))

        return parsed

    # ------------------------------------------------------------------ #
    # 公开 API
    # ------------------------------------------------------------------ #

    def get_items(self, page: int = 1, page_size: int = 20) -> list[dict[str, Any]]:
        """获取自己账号的在售商品列表。

        对应 mtop.idle.web.xyh.item.list，参考 XianyuAutoAsync.get_item_list_info。

        Args:
            page: 页码，从 1 开始。
            page_size: 每页数量。

        Returns:
            商品字典列表，每项含 id/title/price/price_text/status/url/pic_url。
        """
        data = {
            "needGroupInfo": False,
            "pageNumber": page,
            "pageSize": page_size,
            "groupName": "在售",
            "groupId": "58877261",
            "defaultGroup": True,
            "userId": self._user_id,
        }
        res = self._mtop_request(
            "mtop.idle.web.xyh.item.list",
            "1.0",
            data,
            extra_params={
                "spm_cnt": "a21ybx.im.0.0",
                "spm_pre": "a21ybx.collection.menu.1.272b5141NafCNK",
            },
        )
        card_list = (res.get("data") or {}).get("cardList") or []

        items: list[dict[str, Any]] = []
        for card in card_list:
            cd = card.get("cardData") or {}
            if not cd:
                continue
            detail_params = cd.get("detailParams") or {}
            item_id = detail_params.get("itemId") or cd.get("id", "")
            price_info = cd.get("priceInfo") or {}
            pic_info = cd.get("picInfo") or {}
            items.append(
                {
                    "id": item_id,
                    "title": cd.get("title", ""),
                    "price": price_info.get("price", ""),
                    "price_text": (price_info.get("preText", "") or "")
                    + (price_info.get("price", "") or ""),
                    "status": cd.get("itemStatus", 0),
                    "category_id": cd.get("categoryId", ""),
                    "url": "https://www.goofish.com/item?id={}".format(item_id)
                    if item_id
                    else "",
                    "pic_url": pic_info.get("picUrl", ""),
                }
            )
        return items

    def confirm_delivery(self, order_id: str) -> dict[str, Any]:
        """确认订单虚拟发货。

        对应 mtop.taobao.idle.logistic.consign.dummy，
        参考 secure_confirm_decrypted.py。

        Args:
            order_id: 闲鱼订单 ID。

        Returns:
            {"success": bool, "order_id": str} 或错误信息。
        """
        data_val = (
            '{"orderId":"' + order_id + '", "tradeText":"", "picList":[],'
            '"newUnconsign":true}'
        )
        # 注意：发货接口的 data 是原始 JSON 字符串，签名也基于该字符串，
        # 因此这里绕过 _mtop_request 的 json.dumps，直接复用其签名逻辑。
        t = str(int(time.time() * 1000))
        token = _extract_token(self._cookies)
        sign = _generate_sign(t, token, data_val)

        params = {
            "jsv": "2.7.2",
            "appKey": _APP_KEY,
            "t": t,
            "sign": sign,
            "v": "1.0",
            "type": "originaljson",
            "accountSite": "xianyu",
            "dataType": "json",
            "timeout": "20000",
            "api": "mtop.taobao.idle.logistic.consign.dummy",
            "sessionOption": "AutoLoginOnly",
        }
        query_string = urllib.parse.urlencode(params)
        url = _H5API + "/mtop.taobao.idle.logistic.consign.dummy/1.0/?" + query_string
        body = urllib.parse.urlencode({"data": data_val}).encode("utf-8")

        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("User-Agent", _UA)
        req.add_header("Referer", _REFERER)
        req.add_header("Origin", "https://www.goofish.com")
        req.add_header("Cookie", self._build_cookie_header())
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("Accept", "application/json")
        req.add_header("Accept-Language", "zh-CN,zh;q=0.9")

        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                self._update_cookies_from_response(resp.headers)
                res = json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            return {"success": False, "order_id": order_id, "error": "HTTP {}: {}".format(exc.code, exc.reason)}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "order_id": order_id, "error": str(exc)}

        ret = res.get("ret") or [""]
        ret_msg = ret[0] if ret else ""
        if ret_msg == "SUCCESS::调用成功":
            return {"success": True, "order_id": order_id}
        return {"success": False, "order_id": order_id, "error": ret_msg or "未知错误"}

    # ------------------------------------------------------------------ #
    # 搜索商品（高级版）
    # ------------------------------------------------------------------ #

    def _build_search_filter(
        self,
        price_min: float | None = None,
        price_max: float | None = None,
        publish_days: int | None = None,
        personal_only: bool = True,
    ) -> str:
        """构造 searchFilter（个人闲置 + 上新天数 + 价格区间）。

        移植自 xianyu-auto-reply 的 XianyuSearchClient._build_search_filter。
        多个条件以分号拼接。
        """
        parts: list[str] = []
        if personal_only:
            parts.append("quickFilter:filterPersonal;")
        if publish_days:
            try:
                days = int(publish_days)
                if days > 0:
                    parts.append(f"publishDays:{days};")
            except (TypeError, ValueError):
                pass
        if price_min is not None or price_max is not None:
            lo = "" if price_min is None else (
                str(int(price_min)) if float(price_min).is_integer() else str(price_min)
            )
            hi = "undefined" if price_max is None else (
                str(int(price_max)) if float(price_max).is_integer() else str(price_max)
            )
            parts.append(f"priceRange:{lo},{hi};")
        return "".join(parts)

    def search_products(
        self,
        keyword: str,
        page: int = 1,
        page_size: int = 20,
        *,
        price_min: float | None = None,
        price_max: float | None = None,
        publish_days: int | None = None,
        personal_only: bool = True,
        sort_field: str = "",
        sort_value: str = "",
    ) -> list[dict[str, Any]]:
        """搜索闲鱼商品（高级版）。

        对应 mtop.taobao.idlemtopsearch.pc.search，移植自 xianyu-auto-reply
        的 XianyuSearchClient.search，支持价格区间、个人卖家过滤、上新天数、排序。

        Args:
            keyword: 搜索关键词。
            page: 页码，从 1 开始。
            page_size: 每页数量。
            price_min: 最低价格（可选）。
            price_max: 最高价格（可选）。
            publish_days: 只看 N 天内新上架的商品（可选）。
            personal_only: True=只看个人卖家闲置，False=全部（含商家）。
            sort_field: 排序字段，如 "sort_time"（按上新时间）、"sort_price"（按价格）。
            sort_value: 排序值，如 "pubTime"、"price"。

        Returns:
            商品字典列表，每项含丰富的商品信息（id/title/price/area/seller/
            seller_user_id/want_count/tags/publish_time/pic_url/url）。
        """
        search_filter = self._build_search_filter(
            price_min, price_max, publish_days, personal_only
        )
        # 与 xianyu-auto-reply 完全一致的请求格式
        data = {
            "pageNumber": page,
            "keyword": keyword,
            "fromFilter": bool(sort_field or search_filter),
            "rowsPerPage": page_size,
            "sortValue": sort_value or "",
            "sortField": sort_field or "",
            "customDistance": "",
            "gps": "",
            "propValueStr": {"searchFilter": search_filter},
            "customGps": "",
            "searchReqFromPage": "pcSearch",
            "extraFilterValue": "{}",
            "userPositionJson": "{}",
        }
        res = self._mtop_request(
            "mtop.taobao.idlemtopsearch.pc.search",
            "1.0",
            data,
            extra_params={
                "spm_cnt": "a21ybx.search.0.0",
                "spm_pre": "a21ybx.home.searchInput.0",
            },
        )
        result_list = (res.get("data") or {}).get("resultList") or []

        items: list[dict[str, Any]] = []
        for entry in result_list:
            parsed = _parse_search_item(entry)
            if parsed:
                items.append(parsed)
        return items

    # ------------------------------------------------------------------ #
    # 商品详情
    # ------------------------------------------------------------------ #

    def get_item_detail(self, item_id: str) -> dict[str, Any]:
        """获取闲鱼商品详情。

        对应 mtop.taobao.idle.pc.detail，移植自 xianyu-auto-reply
        的 XianyuItemDetailClient.get_detail。

        Args:
            item_id: 闲鱼商品 ID。

        Returns:
            {
              success: bool,
              seller_user_id: str|None,
              seller_nick: str|None,
              title: str|None,
              price: str|None,
              area: str|None,
              desc: str|None,
              detail: dict,        # 原始详情数据（含规格、图片列表等）
            }
        """
        try:
            res = self._mtop_request(
                "mtop.taobao.idle.pc.detail",
                "1.0",
                {"itemId": str(item_id)},
                extra_params={"spm_cnt": "a21ybx.item.0.0"},
            )
        except XianyuError:
            return {"success": False, "item_id": item_id, "error": "详情获取失败"}

        detail = (res.get("data") or {}).get("data", {}) or {}
        # 兼容两种返回结构：有些版本直接在 data 下，有些在 data.data 下
        if not detail:
            detail = (res.get("data") or {})

        seller = detail.get("sellerDO") or {}
        item_do = detail.get("itemDO") or {}

        return {
            "success": True,
            "item_id": str(item_id),
            "title": item_do.get("title", ""),
            "price": str(item_do.get("soldPrice", "")),
            "area": item_do.get("area", ""),
            "desc": item_do.get("desc", ""),
            "seller_user_id": str(seller.get("sellerId", "")) if seller.get("sellerId") else None,
            "seller_nick": seller.get("nick", ""),
            "seller_avatar": seller.get("avatarUrl", ""),
            "pic_urls": [p.get("url", "") for p in (item_do.get("picUrls") or []) if isinstance(p, dict)],
            "detail": detail,
        }


# ── 搜索结果解析函数（移植自 xianyu-auto-reply） ────────────────────────


def _extract_seller_user_id_from_pic(pic_url: str | None) -> str | None:
    """从商品主图 picUrl 中提取卖家真实数字用户ID。

    闲鱼/淘宝图片 CDN 约定：卖家上传的商品主图路径形如
    /bao/uploaded/i{N}/{sellerUserId}/O1CN...，其中 {sellerUserId} 即卖家
    真实数字用户ID。平台图等无该路径段，返回 None。
    """
    if not pic_url:
        return None
    matched = re.search(r"/bao/uploaded/i\d+/(\d+)/O1CN", str(pic_url))
    return matched.group(1) if matched else None


def _parse_search_item(result_entry: dict) -> dict[str, Any] | None:
    """从搜索结果单项中解析出商品关键信息。

    移植自 xianyu-auto-reply 的 parse_search_item，提取丰富的商品数据
    供 AI 综合评价。
    """
    try:
        main = (((result_entry or {}).get("data") or {}).get("item") or {}).get("main") or {}
    except Exception:  # noqa: BLE001
        return None
    if not main:
        return None

    ex_content = main.get("exContent") or {}
    click_args = ((main.get("clickParam") or {}).get("args")) or {}

    item_id = str(ex_content.get("itemId") or click_args.get("item_id") or click_args.get("id") or "").strip()
    if not item_id:
        return None

    title = ex_content.get("title") or (ex_content.get("detailParams") or {}).get("title")
    # 价格：优先取 clickParam.args 里的纯数字价格，其次 detailParams.soldPrice，
    # 最后解析 exContent.price 富文本数组
    price = click_args.get("price") or click_args.get("displayPrice")
    if not price:
        price = (ex_content.get("detailParams") or {}).get("soldPrice")
    if not price:
        raw_price = ex_content.get("price")
        if isinstance(raw_price, list):
            price = "".join(
                str(seg.get("text", ""))
                for seg in raw_price
                if isinstance(seg, dict) and seg.get("type") in ("integer", "decimal")
            )
        elif isinstance(raw_price, (str, int, float)):
            price = str(raw_price)

    area = ex_content.get("area")
    pic_url = ex_content.get("picUrl")
    seller_nick = ex_content.get("userNickName") or (ex_content.get("detailParams") or {}).get("userNick")
    seller_id = click_args.get("seller_id")
    seller_avatar = ex_content.get("userAvatarUrl")
    publish_time = click_args.get("publishTime")
    target_url = main.get("targetUrl")

    # 营销标签与真实想要数：搜索结果的 wantNum 恒为 0 不可靠，
    # 真实想要数藏在 clickParam.args.serviceUtParams 的 content 中。
    tags: list[str] = []
    want_count: str | None = None
    service_ut = click_args.get("serviceUtParams")
    if service_ut:
        try:
            ut_list = json.loads(service_ut) if isinstance(service_ut, str) else service_ut
        except (ValueError, TypeError):
            ut_list = None
        for ut in ut_list or []:
            content = ((ut or {}).get("args") or {}).get("content")
            if not content:
                continue
            content = str(content).strip()
            if content and content not in tags:
                tags.append(content)
            if want_count is None:
                matched = re.search(r"(\d+)\s*人?想要", content)
                if matched:
                    want_count = matched.group(1)
    tags_text = ",".join(tags) if tags else None

    # 发布时间格式化
    publish_time_str = ""
    if str(publish_time).isdigit():
        try:
            publish_time_str = time.strftime(
                "%Y-%m-%d %H:%M", time.localtime(int(publish_time) / 1000)
            )
        except (ValueError, OSError):
            pass

    link = (target_url or "").replace("fleamarket://", "https://www.goofish.com/")
    if not link and item_id:
        link = "https://www.goofish.com/item?id={}".format(item_id)

    pic_full = pic_url or ""
    if pic_full and not pic_full.startswith("http"):
        pic_full = "https:" + pic_full

    return {
        "item_id": item_id,
        "title": str(title) if title else "",
        "price": str(price) if price else "",
        "area": str(area) if area else "",
        "pic_url": pic_full,
        "seller_id": str(seller_id) if seller_id else "",
        "seller_user_id": _extract_seller_user_id_from_pic(pic_url),
        "seller_nick": str(seller_nick) if seller_nick else "",
        "seller_avatar": str(seller_avatar) if seller_avatar else "",
        "want_count": want_count or "",
        "tags": tags_text or "",
        "publish_time": publish_time_str,
        "publish_time_ms": str(publish_time) if publish_time else "",
        "url": link,
    }
