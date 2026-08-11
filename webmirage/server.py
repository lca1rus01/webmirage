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

# ── Platform registry ────────────────────────────────────────────────────
# To add a new platform, import its tools class and add it here.
ALL_PLATFORMS: list[PlatformTools] = [
    TwitterTools(),
    XueqiuTools(),
    XianyuTools(),
    # RedditTools(),      # future
    # YouTubeTools(),     # future
]


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
    server = Server("webmirage")
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

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        """Return all available tools to the MCP client."""
        return [
            types.Tool(
                name=tool_def["name"],
                description=tool_def["description"],
                inputSchema=tool_def["inputSchema"],
            )
            for tool_def in all_tool_defs
        ]

    @server.call_tool()
    async def call_tool(
        name: str,
        arguments: dict[str, Any] | None,
    ) -> list[types.TextContent]:
        """Dispatch a tool call to the appropriate platform handler."""
        arguments = arguments or {}

        if name not in platform_by_tool:
            available_names = [td["name"] for td in all_tool_defs]
            return [
                types.TextContent(
                    type="text",
                    text=(
                        "Error: Unknown tool '{}'. "
                        "Available tools: {}".format(name, available_names)
                    ),
                )
            ]

        platform = platform_by_tool[name]
        logger.info("Tool call: {} with args: {}", name, arguments)

        try:
            result = await platform.handle_call(name, arguments)
            return [types.TextContent(type="text", text=result)]
        except Exception as exc:
            logger.exception("Tool call failed: {}", name)
            return [
                types.TextContent(
                    type="text",
                    text="Error executing '{}': {}".format(name, exc),
                )
            ]

    return server


async def run_server() -> None:
    """Run the MCP server over stdio transport."""
    server = create_server()
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
