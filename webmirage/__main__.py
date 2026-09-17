"""Entry point: python -m webmirage  or  webmirage

Transports (env WEBMIRAGE_TRANSPORT):
    stdio (default) — for local MCP clients that spawn this process
    sse             — network service; binds WEBMIRAGE_HOST:WEBMIRAGE_PORT
"""

import asyncio
import os
import sys

from loguru import logger

from .server import run_server, run_sse_server


def main() -> None:
    """Run the webmirage MCP server."""
    # Configure logging to stderr (stdout is reserved for MCP protocol)
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}",
    )

    transport = os.environ.get("WEBMIRAGE_TRANSPORT", "stdio").lower()
    if transport == "sse":
        host = os.environ.get("WEBMIRAGE_HOST", "0.0.0.0")
        port = int(os.environ.get("WEBMIRAGE_PORT", "8084"))
        logger.info("Starting webmirage MCP server (SSE) on {}:{}...", host, port)
        asyncio.run(run_sse_server(host, port))
    else:
        logger.info("Starting webmirage MCP server (stdio)...")
        asyncio.run(run_server())


if __name__ == "__main__":
    main()
