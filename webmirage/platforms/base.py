"""Base interface for platform plugins.

Each platform (Twitter, Reddit, YouTube, ...) implements this interface
so the MCP server can discover and register tools uniformly.

To add a new platform:
    1. Create ``webmirage/platforms/<name>/`` package
    2. Implement ``PlatformTools`` subclass in ``tools.py``
    3. Add it to the registry in ``server.py``
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class PlatformTools(ABC):
    """Base class for a platform's tool collection."""

    #: Platform name, e.g. "twitter", "reddit"
    name: str = ""

    #: Human-readable description shown in MCP capabilities
    description: str = ""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this platform is configured and ready to use.

        Returns False if required credentials are missing, so the MCP
        server can skip registration and warn the user.
        """
        ...

    @abstractmethod
    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return MCP tool definitions (name, description, inputSchema).

        Each dict should match the JSON Schema for a tool:
            {
                "name": "twitter_search",
                "description": "Search tweets on Twitter/X",
                "inputSchema": {
                    "type": "object",
                    "properties": { ... },
                    "required": [ ... ],
                },
            }
        """
        ...

    @abstractmethod
    async def handle_call(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Handle a tool invocation.

        Args:
            tool_name: The tool name (one of the names from get_tool_definitions).
            arguments: The tool arguments.

        Returns:
            Text content to return to the AI agent.
        """
        ...
