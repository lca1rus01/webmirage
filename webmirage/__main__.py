"""Entry point: python -m webmirage  or  webmirage"""

import asyncio
import sys

from loguru import logger

from .server import run_server


def main() -> None:
    """Run the webmirage MCP server."""
    # Configure logging to stderr (stdout is reserved for MCP protocol)
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}",
    )

    logger.info("Starting webmirage MCP server...")
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
