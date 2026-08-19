"""Reddit JSON API client.

Reddit's web frontend uses ``.json`` endpoints that return JSON when
accessed with a logged-in session cookie.  Anonymous access is blocked
(403 anti-bot), so a ``reddit_session`` cookie is required.

Cookie strategy (priority order):
    1. Saved cookie string in config (key: reddit_cookie)
    2. Auto-extract from Chrome/Edge (requires browser-cookie3 + prior login)

The ``reddit_session`` cookie is the key session credential.  Get it:
    1. Open https://www.reddit.com in Chrome/Edge (log in)
    2. F12 -> Application -> Cookies -> reddit.com
    3. Find ``reddit_session``, copy its value
    4. Add to ~/.webmirage/config.yaml:
         reddit_cookie: "reddit_session=xxx; ..."
    Or set the env var REDDIT_COOKIE.

Reddit requires a descriptive User-Agent; generic ones get rate-limited.
"""

from __future__ import annotations

import http.cookiejar
import json
import re
import urllib.parse
import urllib.request
from typing import Any, Optional

from loguru import logger

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
_TIMEOUT = 15
_REDDIT_HOME = "https://www.reddit.com"


class RedditError(Exception):
    """Base error for Reddit API failures."""


class RedditClient:
    """Cookie-aware HTTP client for Reddit's JSON API."""

    def __init__(self, cookie_str: str = "") -> None:
        self._cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cookie_jar),
        )
        self._cookie_str = cookie_str
        self._initialized = False

    # ------------------------------------------------------------------ #
    # Cookie management
    # ------------------------------------------------------------------ #

    def _inject_cookie_string(self, cookie_str: str) -> None:
        """Parse a 'name=value; name2=value2' string and inject into the jar."""
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if "=" not in pair:
                continue
            name, _, value = pair.partition("=")
            cookie = http.cookiejar.Cookie(
                version=0,
                name=name.strip(),
                value=value.strip(),
                port=None,
                port_specified=False,
                domain=".reddit.com",
                domain_specified=True,
                domain_initial_dot=True,
                path="/",
                path_specified=True,
                secure=True,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
            )
            self._cookie_jar.set_cookie(cookie)

    def _load_cookies_from_browser(self) -> bool:
        """Try to extract Reddit cookies from local Chrome browser.

        Requires the ``browser-cookie3`` package and that the user has
        logged in to reddit.com in Chrome.  Returns True on success.
        """
        try:
            import browser_cookie3
        except ImportError:
            logger.debug("browser-cookie3 not installed, skipping browser cookie extraction")
            return False

        try:
            for browser_fn in (
                browser_cookie3.chrome,
                browser_cookie3.edge,
            ):
                try:
                    cj = browser_fn(domain_name="reddit.com")
                    has_session = False
                    for cookie in cj:
                        self._cookie_jar.set_cookie(cookie)
                        if cookie.name == "reddit_session":
                            has_session = True
                    if has_session:
                        logger.info("Loaded Reddit cookies from browser (found reddit_session)")
                        return True
                except Exception as exc:
                    logger.debug("Browser cookie extraction failed for {}: {}", browser_fn.__name__, exc)
            logger.warning("Browser cookies found but no reddit_session - user may not be logged in to reddit.com")
            return False
        except Exception as exc:
            logger.warning("Failed to extract browser cookies: {}", exc)
            return False

    def ensure_cookies(self) -> None:
        """Populate session cookies (idempotent).

        Priority:
            1. Saved cookie string from config (reddit_cookie in config.yaml)
            2. Auto-extract from Chrome/Edge (requires browser-cookie3 + login)
            3. Anonymous fallback (may 403 on some endpoints)
        """
        if self._initialized:
            return

        # 1. Config file cookie string
        if self._cookie_str:
            logger.debug("Using Reddit cookies from config")
            self._inject_cookie_string(self._cookie_str)
            self._initialized = True
            return

        # 2. Browser auto-extraction
        if self._load_cookies_from_browser():
            self._initialized = True
            return

        # 3. Anonymous fallback (public endpoints may still work)
        logger.debug("No reddit_session cookie — anonymous mode (some endpoints may 403)")
        self._initialized = True

    def _get_json(self, url: str) -> Any:
        """Fetch *url* with Reddit session cookies and return parsed JSON."""
        self.ensure_cookies()
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": _UA,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        try:
            with self._opener.open(req, timeout=_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                raise RedditError(
                    "Reddit returned 403 (anti-bot). The reddit_session cookie is required.\n"
                    "To fix:\n"
                    "  1. Open https://www.reddit.com in Chrome/Edge\n"
                    "  2. F12 -> Application -> Cookies -> reddit.com\n"
                    "  3. Find 'reddit_session', copy its value\n"
                    "  4. Add to ~/.webmirage/config.yaml:\n"
                    "       reddit_cookie: \"reddit_session=xxx\""
                ) from exc
            if exc.code == 429:
                raise RedditError("Reddit rate limited (429). Please wait a moment and try again.") from exc
            raise

    # ------------------------------------------------------------------ #
    # Public API methods
    # ------------------------------------------------------------------ #

    def search(
        self,
        query: str,
        sort: str = "relevance",
        limit: int = 25,
        subreddit: str = "",
    ) -> list[dict[str, Any]]:
        """Search Reddit posts by keyword.

        Args:
            query:    Search query string.
            sort:      Sort order: relevance, hot, new, top, comments.
            limit:     Max results (default 25, max 100).
            subreddit: Optional — restrict search to a subreddit.

        Returns list of dicts with: id, title, selftext, author, subreddit,
                score, num_comments, upvote_ratio, created_utc, permalink, url,
                is_self, over_18, flair.
        """
        limit = max(1, min(limit, 100))

        if subreddit:
            base = "https://www.reddit.com/r/{}/search.json".format(
                urllib.parse.quote(subreddit, safe="")
            )
            params = urllib.parse.urlencode({
                "q": query,
                "sort": sort,
                "limit": str(limit),
                "restrict_sr": "1",
                "sr_detail": "1",
            })
        else:
            base = "https://www.reddit.com/search.json"
            params = urllib.parse.urlencode({
                "q": query,
                "sort": sort,
                "limit": str(limit),
            })

        data = self._get_json("{}?{}".format(base, params))
        children = _deep_get(data, "data", "children") or []
        return [_parse_post(c.get("data", {})) for c in children if c.get("kind") == "t3"]

    def get_subreddit_posts(
        self,
        subreddit: str,
        sort: str = "hot",
        limit: int = 25,
        after: str = "",
    ) -> tuple[list[dict[str, Any]], str]:
        """Get posts from a subreddit.

        Args:
            subreddit: Subreddit name (without r/).
            sort:      hot, new, top, rising.
            limit:     Max results (default 25, max 100).
            after:     Pagination cursor from previous call.

        Returns:
            (posts, next_cursor) where posts is a list of dicts and
            next_cursor is the pagination token for the next page.
        """
        limit = max(1, min(limit, 100))
        sub = urllib.parse.quote(subreddit, safe="")
        params_parts = {"limit": str(limit)}
        if after:
            params_parts["after"] = after
        params = urllib.parse.urlencode(params_parts)

        url = "https://www.reddit.com/r/{}/{}.json?{}".format(sub, sort, params)
        data = self._get_json(url)
        children = _deep_get(data, "data", "children") or []
        after = _deep_get(data, "data", "after") or ""
        posts = [_parse_post(c.get("data", {})) for c in children if c.get("kind") == "t3"]
        return posts, after

    def get_post(self, post_id: str, sort: str = "confidence", limit: int = 30) -> dict[str, Any]:
        """Get a specific post with its comments.

        Args:
            post_id: Post ID (e.g. '1abc2de') or full URL.
            sort:    Comment sort: confidence, top, new, controversial, old.
            limit:   Max comments to return (default 30).

        Returns dict with: post (dict), comments (list of dicts).
        """
        # Extract ID from URL if needed
        if "/" in post_id:
            # https://www.reddit.com/r/sub/comments/ID/TITLE/
            matched = re.search(r"/comments/([a-z0-9]+)", post_id)
            if matched:
                post_id = matched.group(1)
            else:
                post_id = post_id.rstrip("/").split("/")[-1]

        params = urllib.parse.urlencode({
            "sort": sort,
            "limit": str(max(1, min(limit, 100))),
        })
        url = "https://www.reddit.com/comments/{}.json?{}".format(post_id, params)
        data = self._get_json(url)

        if not isinstance(data, list) or len(data) < 2:
            return {"post": {}, "comments": []}

        # First element: the post itself
        post_children = _deep_get(data, 0, "data", "children") or []
        post = {}
        if post_children and post_children[0].get("kind") == "t3":
            post = _parse_post(post_children[0].get("data", {}))

        # Second element: comments
        comment_children = _deep_get(data, 1, "data", "children") or []
        comments = [_parse_comment(c.get("data", {})) for c in comment_children if c.get("kind") == "t1"]

        return {"post": post, "comments": comments}

    def get_user_profile(self, username: str) -> dict[str, Any]:
        """Get a Reddit user's profile information.

        Args:
            username: Reddit username (without u/).

        Returns dict with: username, name, created_utc, karma, karma_breakdown,
                is_verified, verified_email, is_gold, icon_img, subreddit_title,
                subreddit_description.
        """
        user = urllib.parse.quote(username, safe="")
        url = "https://www.reddit.com/user/{}/about.json".format(user)
        data = self._get_json(url)
        result = _deep_get(data, "data") or {}

        subreddit = result.get("subreddit") or {}

        return {
            "username": result.get("name", username),
            "id": result.get("id", ""),
            "created_utc": result.get("created_utc", 0),
            "karma_total": (result.get("total_karma") or result.get("link_karma", 0)
                            + result.get("comment_karma", 0)),
            "karma_link": result.get("link_karma", 0),
            "karma_comment": result.get("comment_karma", 0),
            "karma_awardee": result.get("awardee_karma", 0),
            "karma_awarder": result.get("awarder_karma", 0),
            "is_verified": result.get("verified", False),
            "is_gold": result.get("is_gold", False),
            "icon_img": result.get("icon_img", ""),
            "subreddit_title": subreddit.get("title", ""),
            "subreddit_description": subreddit.get("public_description", ""),
        }

    def get_user_posts(self, username: str, limit: int = 25, after: str = "") -> list[dict[str, Any]]:
        """Get a user's recent posts and comments.

        Args:
            username: Reddit username (without u/).
            limit:     Max results (default 25, max 100).
            after:     Pagination cursor from previous call.

        Returns list of dicts with: type (post/comment), id, title/body,
                subreddit, score, created_utc, permalink.
        """
        limit = max(1, min(limit, 100))
        user = urllib.parse.quote(username, safe="")
        params_parts = {"limit": str(limit)}
        if after:
            params_parts["after"] = after
        params = urllib.parse.urlencode(params_parts)

        url = "https://www.reddit.com/user/{}/overview.json?{}".format(user, params)
        data = self._get_json(url)
        children = _deep_get(data, "data", "children") or []
        results: list[dict[str, Any]] = []
        for c in children:
            kind = c.get("kind", "")
            d = c.get("data", {})
            if kind == "t3":
                results.append(_parse_post(d))
            elif kind == "t1":
                results.append(_parse_comment_as_post(d))
        return results


# ── Parsing helpers ──────────────────────────────────────────────────────


def _deep_get(data: Any, *keys: Any, default: Any = None) -> Any:
    """Safely traverse nested dicts/lists."""
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key, default)
        elif isinstance(data, list) and isinstance(key, int):
            data = data[key] if 0 <= key < len(data) else default
        else:
            return default
    return data


def _parse_post(d: dict[str, Any]) -> dict[str, Any]:
    """Parse a Reddit post (t3) data object into a clean dict."""
    permalink = d.get("permalink", "")
    return {
        "id": d.get("id", ""),
        "title": d.get("title", ""),
        "selftext": d.get("selftext", ""),
        "selftext_html": d.get("selftext_html", ""),
        "author": d.get("author", ""),
        "subreddit": d.get("subreddit", ""),
        "subreddit_id": d.get("subreddit_id", ""),
        "score": d.get("score", 0),
        "num_comments": d.get("num_comments", 0),
        "upvote_ratio": d.get("upvote_ratio", 0),
        "created_utc": d.get("created_utc", 0),
        "permalink": permalink,
        "url": d.get("url", ""),
        "is_self": d.get("is_self", False),
        "over_18": d.get("over_18", False),
        "spoiler": d.get("spoiler", False),
        "stickied": d.get("stickied", False),
        "locked": d.get("locked", False),
        "flair": d.get("link_flair_text", ""),
        "thumbnail": d.get("thumbnail", ""),
        "domain": d.get("domain", ""),
        "full_url": "https://www.reddit.com{}".format(permalink) if permalink else "",
    }


def _parse_comment(d: dict[str, Any]) -> dict[str, Any]:
    """Parse a Reddit comment (t1) data object into a clean dict."""
    return {
        "id": d.get("id", ""),
        "author": d.get("author", ""),
        "body": d.get("body", ""),
        "body_html": d.get("body_html", ""),
        "score": d.get("score", 0),
        "created_utc": d.get("created_utc", 0),
        "subreddit": d.get("subreddit", ""),
        "permalink": d.get("permalink", ""),
        "is_op": d.get("is_submitter", False),
        "stickied": d.get("stickied", False),
        "locked": d.get("locked", False),
        "controversiality": d.get("controversiality", 0),
        "replies": _parse_replies(d.get("replies")),
    }


def _parse_replies(replies_data: Any) -> list[dict[str, Any]]:
    """Recursively parse nested comment replies."""
    if isinstance(replies_data, str):
        # Reddit sometimes returns replies as a JSON string
        try:
            replies_data = json.loads(replies_data)
        except (json.JSONDecodeError, ValueError):
            return []

    children = _deep_get(replies_data, "data", "children") or []
    results: list[dict[str, Any]] = []
    for c in children:
        if c.get("kind") == "t1":
            results.append(_parse_comment(c.get("data", {})))
    return results


def _parse_comment_as_post(d: dict[str, Any]) -> dict[str, Any]:
    """Parse a comment (t1) for display in user overview (post-like format)."""
    permalink = d.get("permalink", "")
    return {
        "id": d.get("id", ""),
        "type": "comment",
        "title": "",
        "selftext": d.get("body", ""),
        "author": d.get("author", ""),
        "subreddit": d.get("subreddit", ""),
        "score": d.get("score", 0),
        "num_comments": 0,
        "upvote_ratio": 0,
        "created_utc": d.get("created_utc", 0),
        "permalink": permalink,
        "url": "",
        "is_self": True,
        "over_18": d.get("over_18", False),
        "stickied": d.get("stickied", False),
        "flair": "",
        "full_url": "https://www.reddit.com{}".format(permalink) if permalink else "",
        "domain": "",
    }
