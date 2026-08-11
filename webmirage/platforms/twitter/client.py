"""Twitter GraphQL API client.

Uses cookie authentication + Chrome TLS fingerprint impersonation (curl_cffi)
+ x-client-transaction-id header generation to access Twitter's internal
GraphQL API — the same API that x.com web frontend uses.

Key anti-detection measures:
    - curl_cffi: impersonates Chrome's TLS handshake (JA3/JA4 fingerprint)
    - x_client_transaction: generates x-client-transaction-id header
    - Full cookie forwarding (not just auth_token + ct0)
    - Request timing jitter to avoid pattern detection
    - Rate limit retry with exponential backoff
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
import time
import urllib.parse
from typing import Any, Callable

import bs4
from curl_cffi import requests as cffi_requests
from x_client_transaction import ClientTransaction
from x_client_transaction.utils import (
    generate_headers as gen_ct_headers,
    get_ondemand_file_url,
)

from ... import config as cfg
from .graphql import (
    BEARER_TOKEN_FULL,
    FEATURES,
    build_graphql_url,
    invalidate_query_id,
    resolve_query_id,
    update_features_from_html,
)
from .auth import get_cookies, AuthenticationError

logger = logging.getLogger(__name__)

# ── Session management ───────────────────────────────────────────────────

_session = None


def _best_chrome_target() -> str:
    """Detect the best available Chrome impersonation target at runtime."""
    try:
        from curl_cffi.requests import BrowserType

        available = {e.value for e in BrowserType}
    except ImportError:
        available = set()

    for target in ("chrome131", "chrome133", "chrome130", "chrome136"):
        if target in available:
            return target

    # Fallback: highest chrome* with numeric suffix
    chrome_targets = sorted(
        [v for v in available if v.startswith("chrome") and v.replace("chrome", "").isdigit()],
        key=lambda x: int(x.replace("chrome", "")),
        reverse=True,
    )
    return chrome_targets[0] if chrome_targets else "chrome131"


def get_session():
    """Return shared curl_cffi session with Chrome impersonation."""
    global _session
    if _session is None:
        config = cfg.get_config()
        proxy = config.get("twitter_proxy", "")
        target = _best_chrome_target()
        _session = cffi_requests.Session(
            impersonate=target,
            proxies={"https": proxy, "http": proxy} if proxy else None,
        )
        logger.info("curl_cffi impersonating %s", target)
        if proxy:
            logger.info("Using proxy: %s...", proxy[:20])
    return _session


def _url_fetch(url: str, headers: dict[str, str] | None = None) -> str:
    """Fetch a URL using curl_cffi for consistent TLS fingerprint."""
    session = get_session()
    resp = session.get(url, headers=headers or {}, timeout=30)
    resp.raise_for_status()
    return resp.text


# ── Data models ──────────────────────────────────────────────────────────


class Tweet:
    """Simplified tweet data model."""

    def __init__(self, **kwargs: Any) -> None:
        self.id: str = kwargs.get("id", "")
        self.text: str = kwargs.get("text", "")
        self.created_at: str = kwargs.get("created_at", "")
        self.user_name: str = kwargs.get("user_name", "")
        self.user_screen_name: str = kwargs.get("user_screen_name", "")
        self.likes: int = kwargs.get("likes", 0)
        self.retweets: int = kwargs.get("retweets", 0)
        self.replies: int = kwargs.get("replies", 0)
        self.views: int = kwargs.get("views", 0)
        self.bookmarks: int = kwargs.get("bookmarks", 0)
        self.quote_count: int = kwargs.get("quote_count", 0)
        self.is_retweet: bool = kwargs.get("is_retweet", False)
        self.is_reply: bool = kwargs.get("is_reply", False)
        self.in_reply_to: str = kwargs.get("in_reply_to", "")
        self.media_urls: list[str] = kwargs.get("media_urls", [])
        self.url: str = kwargs.get("url", "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "created_at": self.created_at,
            "user_name": self.user_name,
            "user_screen_name": self.user_screen_name,
            "likes": self.likes,
            "retweets": self.retweets,
            "replies": self.replies,
            "views": self.views,
            "bookmarks": self.bookmarks,
            "url": self.url,
            "media_urls": self.media_urls,
        }

    def to_text(self) -> str:
        """Format as readable text for AI consumption."""
        lines = [
            "@{} ({})".format(self.user_screen_name, self.user_name),
            self.text,
        ]
        stats = []
        if self.likes:
            stats.append("likes: {}".format(self.likes))
        if self.retweets:
            stats.append("retweets: {}".format(self.retweets))
        if self.replies:
            stats.append("replies: {}".format(self.replies))
        if self.views:
            stats.append("views: {}".format(self.views))
        if stats:
            lines.append(" | ".join(stats))
        if self.created_at:
            lines.append("Posted: {}".format(self.created_at))
        if self.url:
            lines.append("URL: {}".format(self.url))
        return "\n".join(lines)


class UserProfile:
    """Simplified user profile data model."""

    def __init__(self, **kwargs: Any) -> None:
        self.id: str = kwargs.get("id", "")
        self.name: str = kwargs.get("name", "")
        self.screen_name: str = kwargs.get("screen_name", "")
        self.bio: str = kwargs.get("bio", "")
        self.location: str = kwargs.get("location", "")
        self.url: str = kwargs.get("url", "")
        self.followers_count: int = kwargs.get("followers_count", 0)
        self.following_count: int = kwargs.get("following_count", 0)
        self.tweets_count: int = kwargs.get("tweets_count", 0)
        self.likes_count: int = kwargs.get("likes_count", 0)
        self.verified: bool = kwargs.get("verified", False)
        self.profile_image_url: str = kwargs.get("profile_image_url", "")
        self.created_at: str = kwargs.get("created_at", "")

    def to_text(self) -> str:
        lines = [
            "Name: {} (@{})".format(self.name, self.screen_name),
        ]
        if self.bio:
            lines.append("Bio: {}".format(self.bio))
        if self.location:
            lines.append("Location: {}".format(self.location))
        if self.url:
            lines.append("URL: {}".format(self.url))
        lines.append("Followers: {}".format(self.followers_count))
        lines.append("Following: {}".format(self.following_count))
        lines.append("Tweets: {}".format(self.tweets_count))
        lines.append("Likes: {}".format(self.likes_count))
        if self.verified:
            lines.append("Verified: Yes")
        if self.created_at:
            lines.append("Joined: {}".format(self.created_at))
        return "\n".join(lines)


# ── Response parsing helpers ──────────────────────────────────────────────


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


def _parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_twitter_time(time_str: str) -> float:
    """Parse Twitter's created_at format into a sortable timestamp.

    Format: 'Mon Aug 10 04:12:00 +0000 2026'
    Returns 0.0 on failure so broken entries sort to the end.
    """
    from datetime import datetime

    try:
        dt = datetime.strptime(time_str, "%a %b %d %H:%M:%S %z %Y")
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0.0


def parse_tweet_result(result: dict[str, Any]) -> Tweet | None:
    """Parse a tweet result object from GraphQL response."""
    if not result:
        return None

    legacy = result.get("legacy", {}) or {}
    core = result.get("core", {}) or {}
    user_results = core.get("user_results", {}).get("result", {}) or {}
    user_legacy = user_results.get("legacy", {}) or {}

    # Text
    text = legacy.get("full_text", "")
    # Unescape HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")

    # Media
    media_urls: list[str] = []
    entities = legacy.get("entities", {}) or {}
    for media in entities.get("media", []) or []:
        media_url = media.get("media_url_https") or media.get("media_url", "")
        if media_url:
            media_urls.append(media_url)

    tweet_id = result.get("rest_id") or legacy.get("id_str", "")
    screen_name = user_legacy.get("screen_name", "")

    return Tweet(
        id=tweet_id,
        text=text,
        created_at=legacy.get("created_at", ""),
        user_name=user_legacy.get("name", ""),
        user_screen_name=screen_name,
        likes=_parse_int(legacy.get("favorite_count")),
        retweets=_parse_int(legacy.get("retweet_count")),
        replies=_parse_int(legacy.get("reply_count")),
        views=_parse_int(
            _deep_get(result, "views", "count"),
        ),
        bookmarks=_parse_int(legacy.get("bookmark_count")),
        quote_count=_parse_int(legacy.get("quote_count")),
        is_retweet="retweeted_status_result" in result,
        is_reply=bool(legacy.get("in_reply_to_status_id_str")),
        in_reply_to=legacy.get("in_reply_to_screen_name", ""),
        media_urls=media_urls,
        url="https://x.com/{}/status/{}".format(screen_name, tweet_id) if tweet_id else "",
    )


def parse_user_result(result: dict[str, Any]) -> UserProfile | None:
    """Parse a user result object from GraphQL followers/following response."""
    if not result:
        return None

    legacy = result.get("legacy", {}) or {}
    core = result.get("core", {}) or {}
    avatar = result.get("avatar", {}) or {}
    location_obj = result.get("location", {}) or {}

    return UserProfile(
        id=result.get("rest_id", ""),
        name=core.get("name") or legacy.get("name", ""),
        screen_name=core.get("screen_name") or legacy.get("screen_name", ""),
        bio=legacy.get("description", ""),
        location=location_obj.get("location") or legacy.get("location", ""),
        followers_count=_parse_int(legacy.get("followers_count")),
        following_count=_parse_int(legacy.get("friends_count")),
        tweets_count=_parse_int(legacy.get("statuses_count")),
        likes_count=_parse_int(legacy.get("favourites_count")),
        verified=bool(result.get("is_blue_verified") or legacy.get("verified", False)),
        profile_image_url=avatar.get("image_url")
        or legacy.get("profile_image_url_https", ""),
        created_at=core.get("created_at") or legacy.get("created_at", ""),
    )


def parse_timeline_response(
    data: dict[str, Any],
    get_instructions: Callable[[Any], Any],
) -> tuple[list[Tweet], str | None]:
    """Parse a timeline GraphQL response into (tweets, next_cursor)."""
    instructions = get_instructions(data)
    if not instructions:
        return [], None

    tweets: list[Tweet] = []
    next_cursor: str | None = None

    for instruction in instructions:
        entries = instruction.get("entries", []) if isinstance(instruction, dict) else []

        for entry in entries:
            content = entry.get("content", {}) if isinstance(entry, dict) else {}

            # Check for cursor (pagination)
            if content.get("entryType") == "TimelineTimelineCursor":
                if content.get("cursorType") == "Bottom":
                    next_cursor = content.get("value")
                continue

            # Parse tweet entries
            if content.get("entryType") in ("TimelineTimelineItem", "TimelineTimelineModule"):
                item_content = content.get("itemContent", {})
                if not item_content:
                    # TimelineTimelineModule: entries nested inside items
                    items = content.get("items", [])
                    for item in items:
                        item_content = item.get("item", {}).get("itemContent", {})
                        tweet = _parse_item_content(item_content)
                        if tweet:
                            tweets.append(tweet)
                    continue

                tweet = _parse_item_content(item_content)
                if tweet:
                    tweets.append(tweet)

    return tweets, next_cursor


def _parse_item_content(item_content: dict[str, Any]) -> Tweet | None:
    """Parse a single tweet from itemContent."""
    tweet_results = _deep_get(item_content, "tweet_results", "result")
    if not tweet_results:
        # Could be a tombstone (deleted tweet)
        return None

    # Handle TweetWithVisibilityResults wrapper
    if "tweet" in tweet_results:
        tweet_results = tweet_results["tweet"]

    return parse_tweet_result(tweet_results)


# ── TwitterClient ────────────────────────────────────────────────────────


class TwitterClient:
    """Twitter GraphQL API client using cookie authentication."""

    def __init__(self, rate_limit_config: dict[str, Any] | None = None) -> None:
        cookies = get_cookies()
        self._auth_token = cookies["auth_token"]
        self._ct0 = cookies["ct0"]
        self._cookie_string = cookies.get("cookie_string", "")

        rl = rate_limit_config or {}
        self._request_delay = float(rl.get("request_delay", 2.5))
        self._max_retries = int(rl.get("max_retries", 3))
        self._retry_base_delay = float(rl.get("retry_base_delay", 5.0))
        self._max_count = min(int(rl.get("max_count", 50)), 500)

        self._client_transaction: ClientTransaction | None = None
        self._ct_init_attempted = False
        self._ensure_client_transaction()

    # ── Read operations ──────────────────────────────────────────────

    def search_tweets(
        self,
        query: str,
        max_results: int = 10,
        product: str = "Top",
    ) -> list[Tweet]:
        """Search tweets by keyword.

        Args:
            query: Search query string.
            max_results: Max number of tweets to return.
            product: Search tab — "Top", "Latest", "People", "Photos", "Videos".
        """
        return self._fetch_timeline(
            "SearchTimeline",
            max_results,
            lambda data: _deep_get(
                data,
                "data",
                "search_by_raw_query",
                "search_timeline",
                "timeline",
                "instructions",
            ),
            extra_variables={
                "rawQuery": query,
                "querySource": "typed_query",
                "product": product,
            },
            override_base_variables=True,
            use_post=True,
        )

    def get_user_posts(self, username: str, max_results: int = 20) -> list[Tweet]:
        """Fetch tweets posted by a user.

        Args:
            username: Twitter screen name (without @).
            max_results: Max number of tweets to return.
        """
        user_id = self._resolve_user_id(username)
        return self._fetch_timeline(
            "UserTweets",
            max_results,
            lambda data: _deep_get(
                data, "data", "user", "result", "timeline", "timeline", "instructions"
            )
            or _deep_get(
                data, "data", "user", "result", "timeline_v2", "timeline", "instructions"
            ),
            extra_variables={
                "userId": user_id,
                "includePromotedContent": True,
                "withQuickPromoteEligibilityTweetFields": True,
                "withVoice": True,
                "withV2Timeline": True,
            },
        )

    def get_user_profile(self, username: str) -> UserProfile:
        """Fetch user profile by screen name."""
        variables = {
            "screen_name": username,
            "withSafetyModeUserFields": True,
        }
        features = {
            "hidden_profile_subscriptions_enabled": True,
            "rweb_tipjar_consumption_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "subscriptions_verification_info_is_identity_verified_enabled": True,
            "subscriptions_verification_info_verified_since_enabled": True,
            "highlights_tweets_tab_ui_enabled": True,
            "responsive_web_twitter_article_notes_tab_enabled": True,
            "subscriptions_feature_can_gift_premium": True,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True,
        }
        data = self._graphql_get("UserByScreenName", variables, features)
        result = _deep_get(data, "data", "user", "result")
        if not result:
            raise ValueError("User @{} not found".format(username))

        legacy = result.get("legacy", {}) or {}
        core = result.get("core", {}) or {}
        avatar = result.get("avatar", {}) or {}
        location_obj = result.get("location", {}) or {}

        return UserProfile(
            id=result.get("rest_id", ""),
            name=core.get("name") or legacy.get("name", ""),
            screen_name=core.get("screen_name") or legacy.get("screen_name", username),
            bio=legacy.get("description", ""),
            location=location_obj.get("location") or legacy.get("location", ""),
            url=_deep_get(legacy, "entities", "url", "urls", 0, "expanded_url") or "",
            followers_count=_parse_int(legacy.get("followers_count")),
            following_count=_parse_int(legacy.get("friends_count")),
            tweets_count=_parse_int(legacy.get("statuses_count")),
            likes_count=_parse_int(legacy.get("favourites_count")),
            verified=bool(result.get("is_blue_verified") or legacy.get("verified", False)),
            profile_image_url=avatar.get("image_url")
            or legacy.get("profile_image_url_https", ""),
            created_at=core.get("created_at") or legacy.get("created_at", ""),
        )

    def get_me(self) -> UserProfile:
        """Identify the currently authenticated user from cookies.

        Uses the 1.1 account/multi/list endpoint to get the screen name,
        then fetches the full profile via GraphQL.
        """
        url = "https://x.com/i/api/1.1/account/multi/list.json"
        data = self._api_get(url)

        screen_name = None
        if isinstance(data, dict) and "users" in data:
            users = data["users"]
            if isinstance(users, list) and users:
                screen_name = users[0].get("screen_name")
        elif isinstance(data, list) and data:
            user_data = data[0].get("user", {})
            if user_data.get("followers_count") is not None:
                return UserProfile(
                    id=str(user_data.get("id_str", "")),
                    name=user_data.get("name", ""),
                    screen_name=user_data.get("screen_name", ""),
                    bio=user_data.get("description", ""),
                    location=user_data.get("location", ""),
                    followers_count=_parse_int(user_data.get("followers_count")),
                    following_count=_parse_int(user_data.get("friends_count")),
                    tweets_count=_parse_int(user_data.get("statuses_count")),
                    likes_count=_parse_int(user_data.get("favourites_count")),
                    verified=bool(user_data.get("verified", False)),
                    profile_image_url=user_data.get("profile_image_url_https", ""),
                    created_at=user_data.get("created_at", ""),
                )
            screen_name = user_data.get("screen_name", "")

        if screen_name:
            logger.info("Authenticated user: @%s", screen_name)
            return self.get_user_profile(screen_name)

        raise TwitterAPIError(0, "Failed to identify authenticated user")

    def get_following(
        self, username: str, max_results: int = 20
    ) -> list[UserProfile]:
        """Fetch users that a given user is following.

        Args:
            username: Twitter screen name without @.
            max_results: Max number of users to return.
        """
        user_id = self._resolve_user_id(username)
        return self._fetch_user_list(
            "Following",
            user_id,
            max_results,
            lambda data: _deep_get(
                data, "data", "user", "result", "timeline", "timeline", "instructions"
            ),
            use_post=True,
        )

    def get_followers(
        self, username: str, max_results: int = 20
    ) -> list[UserProfile]:
        """Fetch followers of a given user.

        Args:
            username: Twitter screen name without @.
            max_results: Max number of users to return.
        """
        user_id = self._resolve_user_id(username)
        return self._fetch_user_list(
            "Followers",
            user_id,
            max_results,
            lambda data: _deep_get(
                data, "data", "user", "result", "timeline", "timeline", "instructions"
            ),
            use_post=True,
        )

    def get_feed(self, max_per_user: int = 5) -> list[Tweet]:
        """Fetch latest tweets from all configured watchlist accounts.

        Reads the ``twitter_watchlist`` config key and fetches recent
        tweets from each account, then merges and sorts by time
        (most recent first).

        Args:
            max_per_user: Max tweets to fetch per account.

        Returns:
            List of tweets sorted by created_at descending.
        """
        watchlist = cfg.get_config().get("twitter_watchlist", [])
        if not watchlist:
            logger.warning("twitter_watchlist is empty — configure it in ~/.webmirage/config.yaml")
            return []

        all_tweets: list[Tweet] = []
        for username in watchlist:
            username = str(username).lstrip("@")
            try:
                tweets = self.get_user_posts(username, max_results=max_per_user)
                all_tweets.extend(tweets)
                logger.info("Fetched {} tweets from @{}", len(tweets), username)
            except Exception as exc:
                logger.warning("Failed to fetch @{}: {}", username, exc)

        # Sort by created_at descending (most recent first)
        all_tweets.sort(key=lambda t: _parse_twitter_time(t.created_at), reverse=True)
        return all_tweets

    def get_tweet_detail(self, tweet_id: str, max_results: int = 20) -> list[Tweet]:
        """Fetch a tweet and its conversation thread (replies).

        Args:
            tweet_id: Tweet ID (numeric string or full URL).
            max_results: Max number of tweets/replies to return.
        """
        # Extract ID from URL if needed
        if "/" in tweet_id:
            # https://x.com/user/status/1234567890 -> 1234567890
            tweet_id = tweet_id.rstrip("/").split("/")[-1]

        return self._fetch_timeline(
            "TweetDetail",
            max_results,
            lambda data: _deep_get(
                data, "data", "tweetResult", "result", "timeline", "instructions"
            )
            or _deep_get(
                data, "data", "threaded_conversation_with_injections_v2", "instructions"
            ),
            extra_variables={
                "focalTweetId": tweet_id,
                "referrer": "tweet",
                "with_rux_injections": False,
                "includePromotedContent": True,
                "rankingMode": "Relevance",
                "withCommunity": True,
                "withQuickPromoteEligibilityTweetFields": True,
                "withBirdwatchNotes": True,
                "withVoice": True,
            },
            override_base_variables=True,
            field_toggles={
                "withArticleRichContentState": True,
                "withArticlePlainText": False,
            },
        )

    # ── Internal: user ID resolution ─────────────────────────────────

    def _resolve_user_id(self, identifier: str) -> str:
        """Resolve a screen name to numeric user_id."""
        if identifier.isdigit():
            return identifier
        # Strip leading @
        identifier = identifier.lstrip("@")
        profile = self.get_user_profile(identifier)
        return profile.id

    # ── Internal: timeline fetcher with pagination ───────────────────

    def _fetch_timeline(
        self,
        operation_name: str,
        count: int,
        get_instructions: Callable[[Any], Any],
        extra_variables: dict[str, Any] | None = None,
        override_base_variables: bool = False,
        field_toggles: dict[str, Any] | None = None,
        use_post: bool = False,
    ) -> list[Tweet]:
        """Generic timeline fetcher with pagination and deduplication."""
        if count <= 0:
            return []
        count = min(count, self._max_count)

        tweets: list[Tweet] = []
        seen_ids: set[str] = set()
        cursor: str | None = None
        attempts = 0
        max_attempts = int(math.ceil(count / 20.0)) + 2

        while len(tweets) < count and attempts < max_attempts:
            attempts += 1

            variables: dict[str, Any]
            if override_base_variables:
                variables = {"count": min(count - len(tweets) + 5, 40)}
            else:
                variables = {
                    "count": min(count - len(tweets) + 5, 40),
                    "includePromotedContent": False,
                    "latestControlAvailable": True,
                    "requestContext": "launch",
                }
            if extra_variables:
                variables.update(extra_variables)
            if cursor:
                variables["cursor"] = cursor

            if use_post:
                data = self._graphql_post(operation_name, variables, FEATURES)
            else:
                data = self._graphql_get(
                    operation_name, variables, FEATURES, field_toggles=field_toggles
                )

            new_tweets, next_cursor = parse_timeline_response(data, get_instructions)

            for tweet in new_tweets:
                if tweet.id and tweet.id not in seen_ids:
                    seen_ids.add(tweet.id)
                    tweets.append(tweet)

            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

            # Rate-limit: sleep between paginated requests
            if len(tweets) < count and self._request_delay > 0:
                jitter = self._request_delay * random.uniform(0.7, 1.5)
                logger.debug("Sleeping %.1fs between requests", jitter)
                time.sleep(jitter)

        return tweets[:count]

    def _fetch_user_list(
        self,
        operation_name: str,
        user_id: str,
        count: int,
        get_instructions: Callable[[Any], Any],
        use_post: bool = False,
    ) -> list[UserProfile]:
        """Generic user list fetcher (followers/following) with pagination."""
        if count <= 0:
            return []
        count = min(count, self._max_count)

        users: list[UserProfile] = []
        seen_ids: set[str] = set()
        cursor: str | None = None
        attempts = 0
        max_attempts = int(math.ceil(count / 20.0)) + 2

        while len(users) < count and attempts < max_attempts:
            attempts += 1
            variables: dict[str, Any] = {
                "userId": user_id,
                "count": min(count - len(users) + 5, 40),
                "includePromotedContent": False,
            }
            if cursor:
                variables["cursor"] = cursor

            if use_post:
                data = self._graphql_post(operation_name, variables, FEATURES)
            else:
                data = self._graphql_get(operation_name, variables, FEATURES)

            instructions = get_instructions(data)
            if not instructions:
                break

            new_users: list[UserProfile] = []
            next_cursor: str | None = None

            for instruction in instructions:
                entries = instruction.get("entries", []) if isinstance(instruction, dict) else []
                for entry in entries:
                    content = entry.get("content", {}) if isinstance(entry, dict) else {}
                    entry_type = content.get("entryType", "")

                    if entry_type == "TimelineTimelineItem":
                        item = content.get("itemContent", {})
                        user_results = _deep_get(item, "user_results", "result")
                        if user_results:
                            user = parse_user_result(user_results)
                            if user:
                                new_users.append(user)
                    elif entry_type == "TimelineTimelineCursor":
                        if content.get("cursorType") == "Bottom":
                            next_cursor = content.get("value")

            for user in new_users:
                if user.id and user.id not in seen_ids:
                    seen_ids.add(user.id)
                    users.append(user)

            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

            if len(users) < count and self._request_delay > 0:
                time.sleep(self._request_delay * random.uniform(0.7, 1.5))

        return users[:count]

    # ── Internal: GraphQL request methods ────────────────────────────

    def _graphql_get(
        self,
        operation_name: str,
        variables: dict[str, Any],
        features: dict[str, bool],
        field_toggles: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Issue GraphQL GET request with automatic stale-fallback retry."""
        query_id = resolve_query_id(operation_name, prefer_fallback=True, url_fetch_fn=_url_fetch)
        url = build_graphql_url(query_id, operation_name, variables, features, field_toggles)

        try:
            return self._api_get(url)
        except TwitterAPIError as exc:
            if exc.status_code in (404, 422):
                logger.info("Retrying %s with live queryId after %d", operation_name, exc.status_code)
                invalidate_query_id(operation_name)
                refreshed_id = resolve_query_id(
                    operation_name, prefer_fallback=False, url_fetch_fn=_url_fetch
                )
                retry_url = build_graphql_url(
                    refreshed_id, operation_name, variables, features, field_toggles
                )
                return self._api_get(retry_url)
            raise

    def _graphql_post(
        self,
        operation_name: str,
        variables: dict[str, Any],
        features: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        """Issue GraphQL POST request with automatic stale-fallback retry."""
        query_id = resolve_query_id(operation_name, prefer_fallback=True, url_fetch_fn=_url_fetch)

        def _do_post(qid: str) -> dict[str, Any]:
            url = "https://x.com/i/api/graphql/{}/{}".format(qid, operation_name)
            body: dict[str, Any] = {"variables": variables, "queryId": qid}
            if features:
                body["features"] = features
            return self._api_request(url, method="POST", body=body)

        try:
            return _do_post(query_id)
        except TwitterAPIError as exc:
            if exc.status_code in (404, 422):
                logger.info("Retrying POST %s with live queryId", operation_name)
                invalidate_query_id(operation_name)
                refreshed = resolve_query_id(
                    operation_name, prefer_fallback=False, url_fetch_fn=_url_fetch
                )
                return _do_post(refreshed)
            raise

    # ── Internal: HTTP request engine ────────────────────────────────

    def _api_get(self, url: str) -> dict[str, Any]:
        return self._api_request(url, method="GET")

    def _api_request(
        self,
        url: str,
        method: str = "GET",
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make authenticated request to Twitter API with retry on rate limits."""
        headers = self._build_headers(url=url, method=method)
        session = get_session()

        for attempt in range(self._max_retries + 1):
            try:
                if method == "POST":
                    response = session.post(url, headers=headers, json=body, timeout=30)
                else:
                    response = session.get(url, headers=headers, timeout=30)

                status_code = response.status_code
                if status_code == 429 and attempt < self._max_retries:
                    wait = self._retry_base_delay * (2**attempt) + random.uniform(0, 2)
                    logger.warning(
                        "Rate limited (429), retrying in %.1fs (attempt %d/%d)",
                        wait,
                        attempt + 1,
                        self._max_retries,
                    )
                    time.sleep(wait)
                    continue

                if status_code >= 400:
                    raise TwitterAPIError(
                        status_code,
                        "Twitter API error {}: {}".format(status_code, response.text[:500]),
                    )

                payload = response.text
            except TwitterAPIError:
                raise
            except Exception as exc:
                raise TwitterAPIError(0, "Network error: {}".format(exc))

            try:
                parsed = json.loads(payload)
            except (json.JSONDecodeError, ValueError):
                raise TwitterAPIError(0, "Invalid JSON response")

            # Check for API-level errors
            if isinstance(parsed, dict) and parsed.get("errors"):
                err = parsed["errors"][0]
                err_code = err.get("code", 0)
                if err_code == 88 and attempt < self._max_retries:
                    # Rate limit via JSON error code
                    wait = self._retry_base_delay * (2**attempt) + random.uniform(0, 2)
                    time.sleep(wait)
                    continue
                raise TwitterAPIError(0, err.get("message", "Unknown error"))

            return parsed

        raise TwitterAPIError(429, "Rate limited after {} retries".format(self._max_retries))

    # ── Internal: Anti-detection / headers ───────────────────────────

    @staticmethod
    def _ct_cache_path() -> str:
        import os

        home = os.path.expanduser("~")
        return os.path.join(home, ".webmirage", "twitter_transaction_cache.json")

    def _load_ct_cache(self) -> bool:
        """Try to load ClientTransaction from cache (1h TTL)."""
        try:
            import os

            cache_path = self._ct_cache_path()
            if not os.path.exists(cache_path):
                return False
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
            if time.time() - cache.get("created_at", 0) > 3600:
                return False
            home_html = cache.get("home_html", "")
            ondemand_text = cache.get("ondemand_text", "")
            if not home_html or not ondemand_text:
                return False
            home_page_response = bs4.BeautifulSoup(home_html, "html.parser")
            self._client_transaction = ClientTransaction(
                home_page_response=home_page_response,
                ondemand_file_response=ondemand_text,
            )
            update_features_from_html(home_html)
            logger.info("ClientTransaction loaded from cache")
            return True
        except Exception as exc:
            logger.debug("Failed to load CT cache: %s", exc)
            return False

    def _save_ct_cache(self, home_html: str, ondemand_text: str) -> None:
        """Save transaction data to cache file."""
        try:
            import os

            cache_path = self._ct_cache_path()
            cache_dir = os.path.dirname(cache_path)
            os.makedirs(cache_dir, exist_ok=True)
            cache = {
                "home_html": home_html,
                "ondemand_text": ondemand_text,
                "created_at": time.time(),
            }
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f)
        except Exception as exc:
            logger.debug("Failed to save CT cache: %s", exc)

    def _ensure_client_transaction(self) -> None:
        """Initialize ClientTransaction for x-client-transaction-id header."""
        if self._ct_init_attempted:
            return
        self._ct_init_attempted = True

        # Try cache first
        if self._load_ct_cache():
            return

        try:
            cffi_session = get_session()
            ct_headers = gen_ct_headers()
            home_page = cffi_session.get("https://x.com", headers=ct_headers, timeout=10)
            home_page_response = bs4.BeautifulSoup(home_page.content, "html.parser")
            ondemand_url = get_ondemand_file_url(response=home_page_response)
            if not ondemand_url:
                raise ValueError("Failed to extract ondemand file URL")
            ondemand_file = cffi_session.get(ondemand_url, headers=ct_headers, timeout=10)
            self._client_transaction = ClientTransaction(
                home_page_response=home_page_response,
                ondemand_file_response=ondemand_file.text,
            )
            logger.info("ClientTransaction initialized")

            # Extract live feature flags
            update_features_from_html(home_page.text)

            # Save to cache
            self._save_ct_cache(home_page.text, ondemand_file.text)
        except Exception as exc:
            logger.warning("Failed to init ClientTransaction: %s", exc)

    def _build_headers(self, url: str = "", method: str = "GET") -> dict[str, str]:
        """Build headers that mimic a real Chrome browser request to x.com."""
        headers = {
            "Authorization": "Bearer {}".format(BEARER_TOKEN_FULL),
            "Cookie": self._cookie_string,
            "X-Csrf-Token": self._ct0,
            "X-Twitter-Active-User": "yes",
            "X-Twitter-Auth-Type": "OAuth2Session",
            "User-Agent": _get_user_agent(),
            "Origin": "https://x.com",
            "Referer": "https://x.com/",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24", "Google Chrome";v="131"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        if method == "POST":
            headers["Content-Type"] = "application/json"
            headers["Referer"] = "https://x.com/compose/post"
            headers["Priority"] = "u=1, i"

        # Generate x-client-transaction-id
        if self._client_transaction and url:
            try:
                path = urllib.parse.urlparse(url).path
                tid = self._client_transaction.generate_transaction_id(method=method, path=path)
                headers["X-Client-Transaction-Id"] = tid
            except Exception as exc:
                logger.debug("Failed to generate transaction id: %s", exc)

        return headers


# ── Exception ────────────────────────────────────────────────────────────


class TwitterAPIError(Exception):
    """Twitter API error."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def _get_user_agent() -> str:
    """Return a Chrome-like User-Agent string."""
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
