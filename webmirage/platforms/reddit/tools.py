"""MCP tool definitions for the Reddit platform.

Exposes five tools to AI agents:
    - reddit_search           : Search Reddit posts by keyword
    - reddit_subreddit_posts   : Get hot/new posts from a subreddit
    - reddit_post              : Read a specific post with comments
    - reddit_user_profile       : Get user profile info
    - reddit_user_posts         : Get a user's recent posts/comments
"""

from __future__ import annotations

import logging
import time
from typing import Any

from loguru import logger

from ..base import PlatformTools
from ... import config as cfg
from .client import RedditClient, RedditError

logger = logging.getLogger(__name__)


class RedditTools(PlatformTools):
    """Reddit platform tools for webmirage MCP server."""

    name = "reddit"
    description = "Search and read Reddit posts, comments, and user profiles"

    def __init__(self) -> None:
        self._client: RedditClient | None = None

    def is_available(self) -> bool:
        """Reddit is always available - anonymous fallback works for some endpoints."""
        return True

    def _get_client(self) -> RedditClient:
        """Get or create a lazy-initialized RedditClient."""
        if self._client is None:
            config = cfg.get_config()
            self._client = RedditClient(
                cookie_str=config.get("reddit_cookie", ""),
            )
        return self._client

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return the five MCP tool definitions."""
        return [
            {
                "name": "reddit_search",
                "description": (
                    "Search Reddit posts by keyword. Returns matching posts with "
                    "title, body text, author, subreddit, score, comment count, "
                    "and direct URLs.\n\n"
                    "Use this when the user wants to:\n"
                    "- Search what people are saying about a topic on Reddit\n"
                    "- Find discussions mentioning a product, person, or bug\n"
                    "- See community opinions on a specific subject\n\n"
                    "Supports optional subreddit restriction for targeted search."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (supports Reddit search operators)",
                        },
                        "sort": {
                            "type": "string",
                            "description": "Sort order: relevance (default), hot, new, top, comments",
                            "default": "relevance",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results to return (default: 25, max: 100)",
                            "default": 25,
                        },
                        "subreddit": {
                            "type": "string",
                            "description": "Optional: restrict search to a specific subreddit (without r/)",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "reddit_subreddit_posts",
                "description": (
                    "Get posts from a subreddit (hot, new, top, rising). "
                    "Returns posts with title, body text, author, score, "
                    "comment count, and direct URLs.\n\n"
                    "Use this when the user wants to:\n"
                    "- Browse what's trending in a subreddit\n"
                    "- See the latest posts in a community\n"
                    "- Get hot discussions from a specific subreddit"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "subreddit": {
                            "type": "string",
                            "description": "Subreddit name without r/ (e.g. 'MachineLearning', 'python')",
                        },
                        "sort": {
                            "type": "string",
                            "description": "Sort: hot (default), new, top, rising",
                            "default": "hot",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max posts to return (default: 25, max: 100)",
                            "default": 25,
                        },
                    },
                    "required": ["subreddit"],
                },
            },
            {
                "name": "reddit_post",
                "description": (
                    "Read a specific Reddit post and its comments. "
                    "Provide a post ID or full Reddit URL.\n\n"
                    "Use this when the user wants to:\n"
                    "- Read a specific Reddit post they have a link to\n"
                    "- See the discussion and comments under a post\n"
                    "- Get the full body text of a post"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "post_id": {
                            "type": "string",
                            "description": "Post ID (e.g. '1abc2de') or full URL (e.g. 'https://www.reddit.com/r/.../comments/1abc2de/...')",
                        },
                        "sort": {
                            "type": "string",
                            "description": "Comment sort: confidence (default), top, new, controversial, old",
                            "default": "confidence",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max comments to return (default: 30, max: 100)",
                            "default": 30,
                        },
                    },
                    "required": ["post_id"],
                },
            },
            {
                "name": "reddit_user_profile",
                "description": (
                    "Get a Reddit user's profile information. "
                    "Returns username, karma (total, link, comment), account age, "
                    "verification status, and profile description.\n\n"
                    "Use this when the user wants to:\n"
                    "- Learn about a Reddit user\n"
                    "- Check someone's karma or account age\n"
                    "- See a user's profile bio"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "Reddit username (without u/)",
                        },
                    },
                    "required": ["username"],
                },
            },
            {
                "name": "reddit_user_posts",
                "description": (
                    "Get a Reddit user's recent posts and comments. "
                    "Returns their latest activity with post/comment content, "
                    "subreddit, score, and direct URLs.\n\n"
                    "Use this when the user wants to:\n"
                    "- See what a user has been posting recently\n"
                    "- Find a user's comment history\n"
                    "- Monitor a user's activity"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "Reddit username (without u/)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results to return (default: 25, max: 100)",
                            "default": 25,
                        },
                    },
                    "required": ["username"],
                },
            },
        ]

    async def handle_call(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Dispatch a tool call to the appropriate handler."""
        try:
            client = self._get_client()

            if tool_name == "reddit_search":
                posts = client.search(
                    query=arguments["query"],
                    sort=arguments.get("sort", "relevance"),
                    limit=arguments.get("limit", 25),
                    subreddit=arguments.get("subreddit", ""),
                )
                sub_hint = " in r/{}".format(arguments["subreddit"]) if arguments.get("subreddit") else ""
                return _format_posts(
                    'Search: "{}"{}'.format(arguments["query"], sub_hint),
                    posts,
                )

            elif tool_name == "reddit_subreddit_posts":
                posts, after = client.get_subreddit_posts(
                    subreddit=arguments["subreddit"],
                    sort=arguments.get("sort", "hot"),
                    limit=arguments.get("limit", 25),
                )
                return _format_posts(
                    "r/{} ({})".format(arguments["subreddit"], arguments.get("sort", "hot")),
                    posts,
                )

            elif tool_name == "reddit_post":
                result = client.get_post(
                    post_id=arguments["post_id"],
                    sort=arguments.get("sort", "confidence"),
                    limit=arguments.get("limit", 30),
                )
                return _format_post_detail(result)

            elif tool_name == "reddit_user_profile":
                profile = client.get_user_profile(arguments["username"])
                return _format_profile(profile)

            elif tool_name == "reddit_user_posts":
                posts = client.get_user_posts(
                    username=arguments["username"],
                    limit=arguments.get("limit", 25),
                )
                return _format_posts(
                    "Posts by u/{}".format(arguments["username"]),
                    posts,
                )

            else:
                return "Error: Unknown tool '{}'".format(tool_name)

        except RedditError as exc:
            return "Reddit API error: {}".format(exc)
        except Exception as exc:
            logger.exception("Unexpected error in tool call")
            return "Error: {}".format(exc)


# ── Formatting helpers ───────────────────────────────────────────────────


def _fmt_time(utc_ts: Any) -> str:
    """Format a UTC timestamp into readable date-time string."""
    if not utc_ts or not isinstance(utc_ts, (int, float)):
        return ""
    try:
        return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(utc_ts))
    except (ValueError, OSError):
        return str(utc_ts)


def _fmt_age(utc_ts: Any) -> str:
    """Format a UTC timestamp as a human-readable relative age."""
    if not utc_ts or not isinstance(utc_ts, (int, float)):
        return ""
    try:
        diff = time.time() - utc_ts
        if diff < 3600:
            return "{:.0f}m ago".format(diff / 60)
        if diff < 86400:
            return "{:.0f}h ago".format(diff / 3600)
        if diff < 604800:
            return "{:.0f}d ago".format(diff / 86400)
        return "{:.0f}d ago".format(diff / 86400)
    except (ValueError, OSError):
        return ""


def _fmt_post_summary(p: dict[str, Any], index: int) -> list[str]:
    """Format a single post as lines for the summary view."""
    lines = ["\n--- Post {} ---".format(index)]
    lines.append("Title: {}".format(p.get("title", "") or "(no title)"))

    # Author + subreddit
    author = p.get("author", "")
    subreddit = p.get("subreddit", "")
    if author and subreddit:
        lines.append("By u/{} in r/{}".format(author, subreddit))
    elif author:
        lines.append("By u/{}".format(author))
    elif subreddit:
        lines.append("In r/{}".format(subreddit))

    # Selftext (truncated)
    selftext = p.get("selftext", "")
    if selftext:
        lines.append("Body: {}".format(selftext[:300]))

    # Stats
    score = p.get("score", 0)
    num_comments = p.get("num_comments", 0)
    upvote_ratio = p.get("upvote_ratio", 0)
    ratio_str = " ({:.0%})".format(upvote_ratio) if upvote_ratio else ""
    lines.append("Score: {} | Comments: {}{}".format(score, num_comments, ratio_str))

    # Flair
    flair = p.get("flair", "")
    if flair:
        lines.append("Flair: {}".format(flair))

    # Time
    age = _fmt_age(p.get("created_utc"))
    if age:
        lines.append("Posted: {}".format(age))

    # Flags
    flags = []
    if p.get("over_18"):
        flags.append("NSFW")
    if p.get("spoiler"):
        flags.append("Spoiler")
    if p.get("stickied"):
        flags.append("Stickied")
    if p.get("locked"):
        flags.append("Locked")
    if flags:
        lines.append("Tags: {}".format(", ".join(flags)))

    # URL
    full_url = p.get("full_url", "") or p.get("url", "")
    if full_url:
        lines.append("URL: {}".format(full_url))

    return lines


def _format_posts(header: str, posts: list[dict[str, Any]]) -> str:
    """Format a list of posts as readable text for AI consumption."""
    if not posts:
        return "{}\n\nNo posts found.".format(header)

    lines = ["=" * 50, header, "Found {} posts".format(len(posts)), "=" * 50]

    for i, post in enumerate(posts, 1):
        lines.extend(_fmt_post_summary(post, i))

    return "\n".join(lines)


def _format_post_detail(result: dict[str, Any]) -> str:
    """Format a post with its comments as readable text."""
    post = result.get("post", {})
    comments = result.get("comments", [])

    lines = ["=" * 60]

    # Post title
    title = post.get("title", "") or "(no title)"
    subreddit = post.get("subreddit", "")
    if subreddit:
        lines.append("r/{}: {}".format(subreddit, title))
    else:
        lines.append(title)
    lines.append("=" * 60)

    # Post metadata
    author = post.get("author", "")
    if author:
        lines.append("Author: u/{}".format(author))
    score = post.get("score", 0)
    num_comments = post.get("num_comments", 0)
    upvote_ratio = post.get("upvote_ratio", 0)
    ratio_str = " ({:.0%})".format(upvote_ratio) if upvote_ratio else ""
    lines.append("Score: {} | Comments: {}{}".format(score, num_comments, ratio_str))

    age = _fmt_age(post.get("created_utc"))
    if age:
        lines.append("Posted: {}".format(age))

    full_url = post.get("full_url", "")
    if full_url:
        lines.append("URL: {}".format(full_url))

    # Post body
    selftext = post.get("selftext", "")
    if selftext:
        lines.append("")
        lines.append("--- Post Body ---")
        lines.append(selftext)
    elif not post.get("is_self", True) and post.get("url"):
        lines.append("")
        lines.append("Link: {}".format(post.get("url", "")))

    # Comments
    lines.append("")
    lines.append("--- Comments ({}) ---".format(len(comments)))

    for i, comment in enumerate(comments, 1):
        lines.extend(_fmt_comment(comment, i, depth=1))

    if not comments:
        lines.append("(no comments)")

    return "\n".join(lines)


def _fmt_comment(c: dict[str, Any], index: int, depth: int = 1) -> list[str]:
    """Format a single comment (with optional nested replies) as lines."""
    indent = "  " * (depth - 1)
    lines = ["\n{}. {}u/{} | Score: {}".format(
        indent, "#", c.get("author", "[deleted]"), c.get("score", 0)
    )]

    if c.get("is_op"):
        lines[-1] += " [OP]"

    if c.get("stickied"):
        lines[-1] += " [Stickied]"

    body = c.get("body", "")
    if body:
        # Indent the body text
        for line in body.split("\n"):
            lines.append("{}{}".format(indent + "  ", line))

    # Recursively format replies
    replies = c.get("replies") or []
    for j, reply in enumerate(replies):
        lines.extend(_fmt_comment(reply, j + 1, depth + 1))

    return lines


def _format_profile(profile: dict[str, Any]) -> str:
    """Format a user profile as readable text."""
    lines = [
        "=" * 50,
        "u/{}".format(profile.get("username", "")),
        "=" * 50,
    ]

    karma_total = profile.get("karma_total", 0)
    karma_link = profile.get("karma_link", 0)
    karma_comment = profile.get("karma_comment", 0)
    lines.append("Karma: {} (Link: {} | Comment: {})".format(
        karma_total, karma_link, karma_comment
    ))

    created = profile.get("created_utc", 0)
    if created:
        lines.append("Created: {}".format(_fmt_time(created)))

    if profile.get("is_verified"):
        lines.append("Verified: Yes")
    if profile.get("is_gold"):
        lines.append("Gold: Yes")

    desc = profile.get("subreddit_description", "")
    if desc:
        lines.append("")
        lines.append("Bio: {}".format(desc[:200]))

    icon = profile.get("icon_img", "")
    if icon:
        lines.append("Avatar: {}".format(icon))

    return "\n".join(lines)
