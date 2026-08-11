"""MCP tool definitions for the Twitter/X platform.

Exposes four tools to AI agents:
    - twitter_search       : Search tweets by keyword
    - twitter_user_posts   : Get a user's recent tweets
    - twitter_tweet         : Read a specific tweet with replies
    - twitter_user_profile  : Get user profile info
"""

from __future__ import annotations

import logging
from typing import Any

from loguru import logger

from ..base import PlatformTools
from ... import config as cfg
from .auth import AuthenticationError
from .client import Tweet, TwitterClient, TwitterAPIError

logger = logging.getLogger(__name__)


class TwitterTools(PlatformTools):
    """Twitter/X platform tools for webmirage MCP server."""

    name = "twitter"
    description = "Search and read tweets on Twitter/X"

    def __init__(self) -> None:
        self._client: TwitterClient | None = None

    def is_available(self) -> bool:
        """Check if Twitter credentials are configured."""
        return cfg.is_twitter_configured()

    def _get_client(self) -> TwitterClient:
        """Get or create a lazy-initialized TwitterClient."""
        if self._client is None:
            self._client = TwitterClient(
                rate_limit_config={
                    "request_delay": 2.5,
                    "max_retries": 3,
                    "max_count": 50,
                }
            )
        return self._client

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return the four MCP tool definitions."""
        return [
            {
                "name": "twitter_search",
                "description": (
                    "Search tweets on Twitter/X by keyword. "
                    "Returns matching tweets with full text, author, "
                    "engagement stats (likes, retweets, replies, views), "
                    "and direct URLs.\n\n"
                    "Use this when the user wants to:\n"
                    "- Search what people are saying about a topic\n"
                    "- Find tweets mentioning a product, person, or event\n"
                    "- See public discussion on Twitter/X"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (supports Twitter advanced operators like from:user, since:2024-01-01, lang:en)",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of tweets to return (default: 10, max: 50)",
                            "default": 10,
                        },
                        "search_type": {
                            "type": "string",
                            "description": "Search tab: 'Top' (default) or 'Latest'",
                            "default": "Top",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "twitter_user_posts",
                "description": (
                    "Get recent tweets posted by a specific Twitter/X user. "
                    "Returns the user's latest tweets with full text, "
                    "engagement stats, and URLs.\n\n"
                    "Use this when the user wants to:\n"
                    "- See what someone has been posting recently\n"
                    "- Monitor a specific account's activity\n"
                    "- Read a blogger/influencer's latest tweets"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "Twitter screen name without @ (e.g. 'elonmusk')",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of tweets to return (default: 20, max: 50)",
                            "default": 20,
                        },
                    },
                    "required": ["username"],
                },
            },
            {
                "name": "twitter_tweet",
                "description": (
                    "Read a specific tweet and its replies (conversation thread). "
                    "Provide a tweet ID or full tweet URL.\n\n"
                    "Use this when the user wants to:\n"
                    "- Read a specific tweet they have a link to\n"
                    "- See the replies/discussion under a tweet"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "tweet_id_or_url": {
                            "type": "string",
                            "description": "Tweet ID (e.g. '1234567890') or full URL (e.g. 'https://x.com/user/status/1234567890')",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of tweets/replies to return (default: 20)",
                            "default": 20,
                        },
                    },
                    "required": ["tweet_id_or_url"],
                },
            },
            {
                "name": "twitter_user_profile",
                "description": (
                    "Get a Twitter/X user's profile information. "
                    "Returns name, bio, location, follower/following counts, "
                    "total tweets, verification status, and join date.\n\n"
                    "Use this when the user wants to:\n"
                    "- Learn about a Twitter account\n"
                    "- Check someone's follower count or bio"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "Twitter screen name without @ (e.g. 'elonmusk')",
                        },
                    },
                    "required": ["username"],
                },
            },
            {
                "name": "twitter_me",
                "description": (
                    "Get the authenticated user's own Twitter/X profile. "
                    "No parameters needed — identifies you from your cookies.\n\n"
                    "Use this when the user says:\n"
                    "- 'Who am I on Twitter?'\n"
                    "- 'Show me my profile'\n"
                    "- 'What's my Twitter handle?'"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "twitter_my_following",
                "description": (
                    "Get the list of accounts that the authenticated user (you) follows. "
                    "No parameters needed.\n\n"
                    "Use this when the user says:\n"
                    "- 'Who do I follow?'\n"
                    "- 'Show me my following list'\n"
                    "- 'What accounts am I following?'"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of accounts to return (default: 50)",
                            "default": 50,
                        },
                    },
                },
            },
            {
                "name": "twitter_following",
                "description": (
                    "Get the list of accounts that a specific Twitter/X user follows.\n\n"
                    "Use this when the user says:\n"
                    "- 'Who does @elonmusk follow?'\n"
                    "- 'Show me Trump's following list'"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "Twitter screen name without @ (e.g. 'elonmusk')",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of accounts to return (default: 50)",
                            "default": 50,
                        },
                    },
                    "required": ["username"],
                },
            },
            {
                "name": "twitter_followers",
                "description": (
                    "Get a list of a Twitter/X user's followers (people who follow them).\n\n"
                    "Use this when the user says:\n"
                    "- 'Who follows @elonmusk?'\n"
                    "- 'Show me the followers of @realDonaldTrump'"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "Twitter screen name without @ (e.g. 'elonmusk')",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of accounts to return (default: 20)",
                            "default": 20,
                        },
                    },
                    "required": ["username"],
                },
            },
            {
                "name": "twitter_feed",
                "description": (
                    "Fetch the latest tweets from all configured watchlist accounts at once. "
                    "Accounts are configured in ~/.webmirage/config.yaml under 'twitter_watchlist'. "
                    "Returns tweets merged and sorted by time (most recent first).\n\n"
                    "Use this when the user says:\n"
                    "- 'What's my feed?'\n"
                    "- 'Show me latest from my watchlist'\n"
                    "- '拉取我关注博主的最新推文'\n"
                    "- '看看我监控的账号都说了啥'"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "max_per_user": {
                            "type": "integer",
                            "description": "Max tweets to fetch per account (default: 5)",
                            "default": 5,
                        },
                    },
                },
            },
        ]

    async def handle_call(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Dispatch a tool call to the appropriate handler."""
        try:
            client = self._get_client()

            if tool_name == "twitter_search":
                return _format_tweets(
                    "Search: \"{}\"".format(arguments["query"]),
                    client.search_tweets(
                        query=arguments["query"],
                        max_results=arguments.get("max_results", 10),
                        product=arguments.get("search_type", "Top"),
                    ),
                )

            elif tool_name == "twitter_user_posts":
                return _format_tweets(
                    "Tweets from @{}".format(arguments["username"]),
                    client.get_user_posts(
                        username=arguments["username"],
                        max_results=arguments.get("max_results", 20),
                    ),
                )

            elif tool_name == "twitter_tweet":
                return _format_tweets(
                    "Tweet thread",
                    client.get_tweet_detail(
                        tweet_id=arguments["tweet_id_or_url"],
                        max_results=arguments.get("max_results", 20),
                    ),
                )

            elif tool_name == "twitter_user_profile":
                profile = client.get_user_profile(arguments["username"])
                return profile.to_text()

            elif tool_name == "twitter_me":
                profile = client.get_me()
                return profile.to_text()

            elif tool_name == "twitter_my_following":
                me = client.get_me()
                users = client.get_following(
                    me.screen_name,
                    max_results=arguments.get("max_results", 50),
                )
                return _format_users("Your following list", users)

            elif tool_name == "twitter_following":
                users = client.get_following(
                    arguments["username"],
                    max_results=arguments.get("max_results", 50),
                )
                return _format_users(
                    "Following list of @{}".format(arguments["username"]),
                    users,
                )

            elif tool_name == "twitter_followers":
                users = client.get_followers(
                    arguments["username"],
                    max_results=arguments.get("max_results", 20),
                )
                return _format_users(
                    "Followers of @{}".format(arguments["username"]),
                    users,
                )

            elif tool_name == "twitter_feed":
                tweets = client.get_feed(
                    max_per_user=arguments.get("max_per_user", 5),
                )
                if not tweets:
                    return (
                        "No watchlist configured. Add accounts to "
                        "~/.webmirage/config.yaml:\n"
                        "  twitter_watchlist:\n"
                        "    - TrumpDailyPosts\n"
                        "    - elonmusk\n"
                        "    - realDonaldTrump"
                    )
                return _format_tweets("Watchlist Feed", tweets)

            else:
                return "Error: Unknown tool '{}'".format(tool_name)

        except AuthenticationError as exc:
            return "Authentication error: {}\n\nPlease reconfigure Twitter cookies.".format(exc)
        except TwitterAPIError as exc:
            return "Twitter API error ({}): {}".format(exc.status_code, exc.message)
        except Exception as exc:
            logger.exception("Unexpected error in tool call")
            return "Error: {}".format(exc)


def _format_tweets(header: str, tweets: list[Tweet]) -> str:
    """Format a list of tweets as readable text for AI consumption."""
    if not tweets:
        return "{}\n\nNo tweets found.".format(header)

    lines = ["=" * 50, header, "Found {} tweets".format(len(tweets)), "=" * 50]

    for i, tweet in enumerate(tweets, 1):
        lines.append("\n--- Tweet {} ---".format(i))
        lines.append(tweet.to_text())

    return "\n".join(lines)


def _format_users(header: str, users: list) -> str:
    """Format a list of users as readable text for AI consumption."""
    if not users:
        return "{}\n\nNo accounts found.".format(header)

    lines = ["=" * 50, header, "Found {} accounts".format(len(users)), "=" * 50]

    for i, user in enumerate(users, 1):
        verified = " [verified]" if user.verified else ""
        lines.append("\n{}. @{} ({}){}".format(i, user.screen_name, user.name, verified))
        if user.bio:
            lines.append("   {}".format(user.bio[:100]))
        lines.append("   Followers: {} | Following: {}".format(
            user.followers_count, user.following_count
        ))

    return "\n".join(lines)
