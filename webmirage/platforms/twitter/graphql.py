"""Twitter GraphQL infrastructure.

Handles queryId resolution, URL building, and feature flag management.
Ported from twitter-cli's graphql.py with simplifications.

queryId resolution order:
    1. Hardcoded fallback constants (fastest, may go stale)
    2. Community-maintained twitter-openapi on GitHub
    3. JS bundle scanning from x.com homepage
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── Twitter web client Bearer token (public, embedded in x.com JS) ──────
# This is the same token used by x.com's web frontend — it's not a secret.
# Sourced from twitter-cli/constants.py (the upstream tool Agent-Reach uses).
BEARER_TOKEN_FULL = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# ── Community queryId source ────────────────────────────────────────────
TWITTER_OPENAPI_URL = (
    "https://raw.githubusercontent.com/fa0311/"
    "twitter-openapi/refs/heads/main/src/config/placeholder.json"
)

# ── Fallback (hardcoded) queryIds ────────────────────────────────────────
FALLBACK_QUERY_IDS: dict[str, str] = {
    "HomeTimeline": "c-CzHF1LboFilMpsx4ZCrQ",
    "HomeLatestTimeline": "BKB7oi212Fi7kQtCBGE4zA",
    "UserByScreenName": "1VOOyvKkiI3FMmkeDNxM9A",
    "UserTweets": "q6xj5bs0hapm9309hexA_g",
    "TweetDetail": "xd_EMdYvB9hfZsZ6Idri0w",
    "Likes": "lIDpu_NWL7_VhimGGt0o6A",
    "SearchTimeline": "VhUd6vHVmLBcw0uX-6jMLA",
    "Bookmarks": "2neUNDqrrFzbLui8yallcQ",
    "ListLatestTweetsTimeline": "RlZzktZY_9wJynoepm8ZsA",
    "Followers": "IOh4aS6UdGWGJUYTqliQ7Q",
    "Following": "zx6e-TLzRkeDO_a7p4b3JQ",
    "CreateTweet": "IID9x6WsdMnTlXnzXGq8ng",
    "DeleteTweet": "VaenaVgh5q5ih7kvyVjgtg",
    "FavoriteTweet": "lI07N6Otwv1PhnEgXILM7A",
    "UnfavoriteTweet": "ZYKSe-w7KEslx3JhSIk5LA",
    "TweetResultByRestId": "7xflPyRiUxGVbJd4uWmbfg",
}

# ── Default feature flags ────────────────────────────────────────────────
DEFAULT_FEATURES: dict[str, bool] = {
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "tweetypie_unmention_optimization_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "responsive_web_enhance_cards_enabled": False,
}

# Mutable copy that gets updated dynamically
FEATURES: dict[str, bool] = dict(DEFAULT_FEATURES)

# Module-level caches
_cached_query_ids: dict[str, str] = {}
_bundles_scanned = False


def build_graphql_url(
    query_id: str,
    operation_name: str,
    variables: dict[str, Any],
    features: dict[str, bool],
    field_toggles: dict[str, Any] | None = None,
) -> str:
    """Build a GraphQL GET URL with encoded variables/features/fieldToggles.

    False-valued features are omitted to keep URL under server limits.
    """
    compact_features = {k: v for k, v in features.items() if v is not False}
    url = "https://x.com/i/api/graphql/{}/{}?variables={}&features={}".format(
        query_id,
        operation_name,
        urllib.parse.quote(json.dumps(variables, separators=(",", ":"))),
        urllib.parse.quote(json.dumps(compact_features, separators=(",", ":"))),
    )
    if field_toggles:
        url += "&fieldToggles={}".format(
            urllib.parse.quote(json.dumps(field_toggles, separators=(",", ":")))
        )
    return url


def _fetch_query_id_from_github(
    url_fetch_fn: Callable[[str, dict[str, str]], str],
    operation_name: str,
) -> str | None:
    """Fetch queryId from community-maintained twitter-openapi file."""
    try:
        payload = url_fetch_fn(TWITTER_OPENAPI_URL, {"user-agent": "webmirage/0.1"})
        parsed = json.loads(payload)
        operation = parsed.get(operation_name, {})
        query_id = operation.get("queryId")
        if isinstance(query_id, str) and query_id:
            return query_id
    except Exception as exc:
        logger.debug("GitHub queryId lookup failed for %s: %s", operation_name, exc)
    return None


def _scan_js_bundles(url_fetch_fn: Callable[[str, dict[str, str]], str]) -> None:
    """Scan Twitter JS bundles and cache queryId mappings."""
    global _bundles_scanned
    if _bundles_scanned:
        return
    _bundles_scanned = True

    try:
        html = url_fetch_fn("https://x.com", {"user-agent": "webmirage/0.1"})
        script_pattern = re.compile(
            r'(?:src|href)=["\']'
            r'(https://abs\.twimg\.com/responsive-web/client-web[^"\']+\.js)'
            r'["\']'
        )
        script_urls = script_pattern.findall(html)
    except Exception as exc:
        logger.warning("Failed to scan JS bundles: %s", exc)
        return

    for script_url in script_urls[:10]:  # limit to avoid excessive fetching
        try:
            bundle = url_fetch_fn(script_url, {"user-agent": "webmirage/0.1"})
            op_pattern = re.compile(
                r'queryId:\s*"([A-Za-z0-9_-]+)"[^}]{0,200}'
                r'operationName:\s*"([^"]+)"'
            )
            for match in op_pattern.finditer(bundle):
                query_id, op_name = match.group(1), match.group(2)
                _cached_query_ids.setdefault(op_name, query_id)
        except Exception:
            continue

    logger.info(
        "Scanned %d JS bundles, cached %d query IDs",
        len(script_urls),
        len(_cached_query_ids),
    )


def update_features_from_html(html: str) -> None:
    """Extract live feature flags from x.com HTML and update FEATURES dict.

    Only updates existing keys — never adds new ones.
    """
    try:
        feature_pattern = re.compile(
            r'"([a-z][a-z0-9_]+)":\s*\{\s*"value"\s*:\s*(true|false)',
            re.IGNORECASE,
        )
        found = 0
        for match in feature_pattern.finditer(html):
            key = match.group(1)
            value = match.group(2).lower() == "true"
            if key in FEATURES and FEATURES[key] != value:
                FEATURES[key] = value
                found += 1
        if found:
            logger.info("Updated %d feature flags from x.com", found)
    except Exception as exc:
        logger.debug("Feature extraction from HTML failed: %s", exc)


def invalidate_query_id(operation_name: str) -> None:
    """Remove a cached queryId so it gets re-resolved on next call."""
    _cached_query_ids.pop(operation_name, None)


def resolve_query_id(
    operation_name: str,
    prefer_fallback: bool = True,
    url_fetch_fn: Callable[[str, dict[str, str]], str] | None = None,
) -> str:
    """Resolve queryId using cache, remote sources, and fallback constants.

    Resolution order:
        1. In-memory cache
        2. Hardcoded fallback (if prefer_fallback=True)
        3. Community GitHub source
        4. JS bundle scanning from x.com
        5. Final fallback to hardcoded constants
    """
    cached = _cached_query_ids.get(operation_name)
    if cached:
        return cached

    fallback = FALLBACK_QUERY_IDS.get(operation_name)
    if prefer_fallback and fallback:
        _cached_query_ids[operation_name] = fallback
        return fallback

    if url_fetch_fn:
        # Try community source
        github_id = _fetch_query_id_from_github(url_fetch_fn, operation_name)
        if github_id:
            _cached_query_ids[operation_name] = github_id
            return github_id

        # Try JS bundle scanning
        _scan_js_bundles(url_fetch_fn)
        cached = _cached_query_ids.get(operation_name)
        if cached:
            return cached

    if fallback:
        _cached_query_ids[operation_name] = fallback
        return fallback

    raise RuntimeError('Cannot resolve queryId for "{}"'.format(operation_name))
