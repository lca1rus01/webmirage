"""webmirage MCP server.

Discovers platform plugins, collects their tool definitions, and
serves them over the MCP stdio transport.

Usage:
    python -m webmirage          # run as MCP server (stdio)
    webmirage                    # via console_scripts entry point
"""

from __future__ import annotations

import logging
from typing import Any

import mcp.server.stdio
import mcp.types as types
from loguru import logger
from mcp.server import Server

from .platforms.base import PlatformTools
from .platforms.twitter.tools import TwitterTools
from .platforms.xueqiu.tools import XueqiuTools
from .platforms.xianyu.tools import XianyuTools
from .platforms.reddit.tools import RedditTools
from .platforms.system.tools import SystemTools
from .platforms.github.tools import GitHubTools

# ── Platform registry ────────────────────────────────────────────────────
# To add a new platform, import its tools class and add it here.
_system_tools = SystemTools()

ALL_PLATFORMS: list[PlatformTools] = [
    _system_tools,
    TwitterTools(),
    XueqiuTools(),
    XianyuTools(),
    RedditTools(),
    GitHubTools(),
    # YouTubeTools(),     # future
]


def _reload_all_platforms() -> list[str]:
    """Reload every registered platform (config cache already invalidated).

    Returns the list of platform names whose cached clients were dropped.
    """
    names: list[str] = []
    for platform in ALL_PLATFORMS:
        try:
            platform.reload()
            names.append(platform.name)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to reload platform '{}': {}", platform.name, exc
            )
    return names


_system_tools.set_reload_callback(_reload_all_platforms)


def _discover_platforms() -> tuple[list[PlatformTools], list[str]]:
    """Find all platforms that are configured and ready.

    Returns:
        (available_platforms, warnings)
    """
    available: list[PlatformTools] = []
    warnings: list[str] = []

    for platform in ALL_PLATFORMS:
        if platform.is_available():
            logger.info("Platform '{}' is available", platform.name)
            available.append(platform)
        else:
            msg = "Platform '{}' is not configured — tools will be hidden.".format(
                platform.name
            )
            logger.warning(msg)
            warnings.append(msg)

    return available, warnings


def create_server() -> Server:
    """Create and configure the MCP server with all available platform tools."""
    platforms, warnings = _discover_platforms()

    # Collect all tool definitions from available platforms
    all_tool_defs: list[dict[str, Any]] = []
    platform_by_tool: dict[str, PlatformTools] = {}

    for platform in platforms:
        for tool_def in platform.get_tool_definitions():
            all_tool_defs.append(tool_def)
            platform_by_tool[tool_def["name"]] = platform

    if warnings:
        for msg in warnings:
            logger.warning(msg)

    logger.info(
        "Registered {} tools from {} platform(s): {}",
        len(all_tool_defs),
        len(platforms),
        [p.name for p in platforms],
    )

    async def list_tools(
        _ctx: Any,
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        """Return all available tools to the MCP client."""
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=tool_def["name"],
                    description=tool_def["description"],
                    inputSchema=tool_def["inputSchema"],
                )
                for tool_def in all_tool_defs
            ]
        )

    async def call_tool(
        _ctx: Any,
        request: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        """Dispatch a tool call to the appropriate platform handler."""
        name = request.name
        arguments = request.arguments or {}

        if name not in platform_by_tool:
            available_names = [td["name"] for td in all_tool_defs]
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=(
                            "Error: Unknown tool '{}'. "
                            "Available tools: {}".format(name, available_names)
                        ),
                    )
                ],
                isError=True,
            )

        platform = platform_by_tool[name]
        logger.info("Tool call: {} with args: {}", name, arguments)

        try:
            result = await platform.handle_call(name, arguments)
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=result)]
            )
        except Exception as exc:
            logger.exception("Tool call failed: {}", name)
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text="Error executing '{}': {}".format(name, exc),
                    )
                ],
                isError=True,
            )

    return Server(
        "webmirage",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def run_server() -> None:
    """Run the MCP server over stdio transport."""
    server = create_server()
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
