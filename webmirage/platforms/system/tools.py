"""MCP tool definitions for webmirage system management.

暴露给 AI 的系统工具：

    - webmirage_reload_config : 热重载 ~/.webmirage/config.yaml（无需重启 MCP 服务）

典型场景：用户在浏览器更新了某平台的 cookie 并写入配置文件后，
直接调用本工具即可让运行中的服务立即使用新凭证。
"""

from __future__ import annotations

from typing import Any, Callable

from loguru import logger

from ..base import PlatformTools
from ... import config as cfg


class SystemTools(PlatformTools):
    """webmirage 系统管理工具集。"""

    name = "system"
    description = "webmirage 系统管理：配置热重载"

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
        ]

    async def handle_call(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Dispatch a tool call to the appropriate handler."""
        if tool_name != "webmirage_reload_config":
            return "Error: Unknown system tool '{}'".format(tool_name)

        lines: list[str] = []

        # 1. 重新读取配置文件（mtime 缓存已失效，此处强制加载新值）
        cfg.invalidate_config_cache()
        config = cfg.get_config()
        lines.append("Config reloaded from ~/.webmirage/config.yaml")

        # 2. 凭证概览：哪些平台已配置
        cred_status = []
        for key, label in (
            ("twitter_auth_token", "twitter"),
            ("xueqiu_cookie", "xueqiu"),
            ("xianyu_cookie", "xianyu"),
            ("reddit_cookie", "reddit"),
        ):
            cred_status.append("{}: {}".format(label, "ok" if config.get(key) else "missing"))
        lines.append("Credentials -> " + " | ".join(cred_status))

        # 3. 通知各平台丢弃缓存的 client（下次调用时用新配置重建）
        if self._reload_callback is not None:
            try:
                refreshed = self._reload_callback()
                lines.append(
                    "Platform clients refreshed ({}): {}".format(
                        len(refreshed), ", ".join(refreshed)
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to reload platform clients")
                lines.append("Warning: platform client refresh failed: {}".format(exc))
        else:
            lines.append("Warning: no reload callback registered")

        return "\n".join(lines)
