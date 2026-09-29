"""MCP tool definitions for webmirage system management.

暴露给 AI 的系统工具：

    - webmirage_reload_config : 热重载 ~/.webmirage/config.yaml（无需重启 MCP 服务）
    - webmirage_set_cookie    : 更新平台凭证并立即热重载（无需 SSH / 重启）
    - webmirage_health        : 各平台健康报告（凭证配置 + 最近调用成败）
    - webmirage_proxy_status  : 查看集成 Mihomo 的状态、分组和节点
    - webmirage_proxy_select  : 切换 Mihomo 代理分组的节点

典型场景：用户在浏览器更新了某平台的 cookie，把新值发给 AI，
AI 调用 webmirage_set_cookie 即可让运行中的服务立即使用新凭证。
"""

from __future__ import annotations

from typing import Any, Callable

from loguru import logger

from ..base import PlatformTools
from ... import config as cfg
from ... import health
from ...mihomo import MihomoController, MihomoControllerError

#: 允许通过 webmirage_set_cookie 更新的凭证键（白名单）
_CREDENTIAL_KEYS: dict[str, str] = {
    "twitter_auth_token": "Twitter auth_token",
    "twitter_ct0": "Twitter ct0 cookie",
    "twitter_proxy": "Twitter 代理地址",
    "xueqiu_cookie": "雪球 cookie",
    "xianyu_cookie": "闲鱼 cookie",
    "xianyu_user_id": "闲鱼用户 ID",
    "reddit_cookie": "Reddit cookie",
}

#: 各平台的凭证就绪判断（用于健康报告）
_PLATFORM_CREDS: dict[str, tuple[str, ...]] = {
    "twitter": ("twitter_auth_token", "twitter_ct0"),
    "xueqiu": ("xueqiu_cookie",),
    "xianyu": ("xianyu_cookie",),
    "reddit": ("reddit_cookie",),
    "github": (),  # 匿名可用
}


class SystemTools(PlatformTools):
    """webmirage 系统管理工具集。"""

    name = "system"
    description = "webmirage 系统管理：配置热重载 / 凭证更新 / 平台健康 / Mihomo 代理"

    def __init__(self) -> None:
        # 由 server.py 注入：重载所有平台缓存的回调，返回已刷新的平台名列表
        self._reload_callback: Callable[[], list[str]] | None = None

    def set_reload_callback(self, callback: Callable[[], list[str]]) -> None:
        """Set the callback that reloads all platform clients.

        The callback should call ``reload()`` on every registered platform
        and return the list of platform names that were refreshed.
        """
        self._reload_callback = callback

    def is_available(self) -> bool:
        """系统工具始终可用。"""
        return True

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "webmirage_reload_config",
                "description": (
                    "Reload webmirage configuration from "
                    "~/.webmirage/config.yaml WITHOUT restarting the MCP "
                    "server. Refreshes all cached platform clients so new "
                    "cookies / watchlists take effect immediately.\n\n"
                    "Use this when the user wants to:\n"
                    "- Apply newly updated platform cookies "
                    "(Twitter/Xueqiu/Xianyu/Reddit)\n"
                    "- Refresh watchlist accounts or stock lists\n"
                    "- '重新加载配置' / '刷新cookie' / 'reload config'"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "webmirage_set_cookie",
                "description": (
                    "Update ONE platform credential (cookie / token) in "
                    "~/.webmirage/config.yaml and hot-reload all platform "
                    "clients immediately — no SSH, no server restart.\n\n"
                    "Use when the user provides a fresh credential copied "
                    "from the browser (F12 -> Application -> Cookies), "
                    "e.g. '帮我更新雪球cookie：<新值>' or 'update the "
                    "reddit cookie: <value>'. Pass the value EXACTLY as "
                    "copied, do not truncate or reformat it."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "enum": list(_CREDENTIAL_KEYS),
                            "description": "Which credential to update",
                        },
                        "value": {
                            "type": "string",
                            "description": "New credential value (full string)",
                        },
                    },
                    "required": ["key", "value"],
                },
            },
            {
                "name": "webmirage_health",
                "description": (
                    "Report per-platform health: credential configured or "
                    "not, call counts, time since last successful call, and "
                    "the most recent error.\n\n"
                    "Use to check which platforms are healthy vs which have "
                    "stale cookies BEFORE calling their tools — e.g. when "
                    "the user asks '哪些平台还能用' / 'cookie 还有效吗' / "
                    "'check platform health'."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "webmirage_proxy_status",
                "description": (
                    "Check the integrated Mihomo proxy sidecar: its version, "
                    "selectable proxy groups, current selections, and available nodes. "
                    "No controller secret is returned. Use this before switching nodes "
                    "or when diagnosing proxy connectivity."
                ),
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "webmirage_proxy_select",
                "description": (
                    "Switch ONE Mihomo selector group to ONE node. First call "
                    "webmirage_proxy_status and use its exact group and node names. "
                    "This changes outbound routing immediately, without restarting WebMirage."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "group": {"type": "string", "description": "Exact selector group name"},
                        "node": {"type": "string", "description": "Exact node name from that group"},
                    },
                    "required": ["group", "node"],
                },
            },
        ]

    async def handle_call(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Dispatch a tool call to the appropriate handler."""
        if tool_name == "webmirage_reload_config":
            return self._reload_config()
        if tool_name == "webmirage_set_cookie":
            return self._set_cookie(arguments)
        if tool_name == "webmirage_health":
            return self._health_report()
        if tool_name == "webmirage_proxy_status":
            return self._proxy_status()
        if tool_name == "webmirage_proxy_select":
            return self._proxy_select(arguments)
        return "Error: Unknown system tool '{}'".format(tool_name)

    # ------------------------------------------------------------------ #
    # webmirage_reload_config
    # ------------------------------------------------------------------ #

    def _reload_config(self) -> str:
        lines: list[str] = []

        # 1. 重新读取配置文件（mtime 缓存已失效，此处强制加载新值）
        cfg.invalidate_config_cache()
        config = cfg.get_config()
        lines.append("Config reloaded from ~/.webmirage/config.yaml")

        # 2. 凭证概览：哪些平台已配置
        lines.append("Credentials -> " + self._credentials_summary(config))

        # 3. 通知各平台丢弃缓存的 client（下次调用时用新配置重建）
        lines.append(self._refresh_clients())
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # webmirage_set_cookie
    # ------------------------------------------------------------------ #

    def _set_cookie(self, arguments: dict[str, Any]) -> str:
        key = str(arguments.get("key", "")).strip()
        value = str(arguments.get("value", "")).strip()

        if key not in _CREDENTIAL_KEYS:
            return "Error: unknown credential key '{}'. Valid keys: {}".format(
                key, ", ".join(sorted(_CREDENTIAL_KEYS))
            )
        if not value:
            return "Error: value must not be empty"

        # 1. 持久化到配置文件
        cfg.save_config({key: value})

        # 2. 强制重读 + 校验写入生效
        cfg.invalidate_config_cache()
        config = cfg.get_config()
        if config.get(key) != value:
            return (
                "Error: saved value for '{}' does not match what was read "
                "back — config write may have failed".format(key)
            )

        lines = [
            "Saved {} ({} chars) to ~/.webmirage/config.yaml".format(
                _CREDENTIAL_KEYS[key], len(value)
            ),
            "Credentials -> " + self._credentials_summary(config),
            self._refresh_clients(),
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Integrated Mihomo management
    # ------------------------------------------------------------------ #

    @staticmethod
    def _mihomo_controller() -> MihomoController | None:
        config = cfg.get_config()
        secret = str(config.get("mihomo_api_secret", "")).strip()
        if not secret:
            return None
        return MihomoController(str(config.get("mihomo_controller", "http://mihomo:9090")), secret)

    def _proxy_status(self) -> str:
        controller = self._mihomo_controller()
        if controller is None:
            return "Error: MIHOMO_API_SECRET is not configured; proxy controller access is disabled."
        try:
            status = controller.status()
        except MihomoControllerError as exc:
            return "Error: Mihomo proxy status unavailable: {}".format(exc)

        groups = status["groups"]
        lines = ["Mihomo proxy status: version={}, selector_groups={}".format(status["version"], len(groups))]
        for group in groups:
            candidates = group["candidates"]
            preview = ", ".join(candidates[:25])
            if len(candidates) > 25:
                preview += ", ... ({} total)".format(len(candidates))
            lines.append("- {} [{}] -> {} | nodes: {}".format(group["name"], group["type"], group["selected"] or "(none)", preview or "(none)"))
        return "\n".join(lines)

    def _proxy_select(self, arguments: dict[str, Any]) -> str:
        group = str(arguments.get("group", "")).strip()
        node = str(arguments.get("node", "")).strip()
        if not group or not node:
            return "Error: group and node must both be non-empty"
        controller = self._mihomo_controller()
        if controller is None:
            return "Error: MIHOMO_API_SECRET is not configured; proxy controller access is disabled."
        try:
            status = controller.status()
            selected_group = next((item for item in status["groups"] if item["name"] == group), None)
            if selected_group is None:
                return "Error: proxy group '{}' was not found; call webmirage_proxy_status first.".format(group)
            if node not in selected_group["candidates"]:
                return "Error: node '{}' is not in group '{}'; call webmirage_proxy_status first.".format(node, group)
            controller.select_proxy(group, node)
        except MihomoControllerError as exc:
            return "Error: Mihomo proxy switch failed: {}".format(exc)
        return "Mihomo proxy group '{}' switched to '{}'.".format(group, node)

    # ------------------------------------------------------------------ #
    # webmirage_health
    # ------------------------------------------------------------------ #

    def _health_report(self) -> str:
        config = cfg.get_config()
        snap = health.snapshot()

        lines = ["webmirage platform health:", ""]
        for platform, cred_keys in _PLATFORM_CREDS.items():
            configured = all(config.get(k) for k in cred_keys)
            rec = snap.get(platform)
            if rec is None:
                lines.append(
                    "- {}: credential={}, calls=0 (no traffic since server "
                    "start)".format(platform, "ok" if configured else "MISSING")
                )
                continue
            err = ""
            if rec["last_error_msg"]:
                err = " last_error={}: {}".format(
                    rec["last_error"], rec["last_error_msg"].splitlines()[0][:120]
                )
            lines.append(
                "- {}: credential={}, calls={} (ok={} fail={}), "
                "last_success={}{}".format(
                    platform,
                    "ok" if configured else "MISSING",
                    rec["calls"],
                    rec["ok"],
                    rec["fail"],
                    rec["last_success"],
                    err,
                )
            )
        lines.append("")
        lines.append(
            "Hint: a platform with recent failures and no recent success "
            "usually means its cookie expired — refresh it in the browser "
            "and update via webmirage_set_cookie."
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _credentials_summary(config: dict[str, Any]) -> str:
        parts = []
        for key, label in (
            ("twitter_auth_token", "twitter"),
            ("xueqiu_cookie", "xueqiu"),
            ("xianyu_cookie", "xianyu"),
            ("reddit_cookie", "reddit"),
        ):
            parts.append("{}: {}".format(label, "ok" if config.get(key) else "missing"))
        return " | ".join(parts)

    def _refresh_clients(self) -> str:
        if self._reload_callback is None:
            return "Warning: no reload callback registered"
        try:
            refreshed = self._reload_callback()
            return "Platform clients refreshed ({}): {}".format(
                len(refreshed), ", ".join(refreshed)
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to reload platform clients")
            return "Warning: platform client refresh failed: {}".format(exc)
