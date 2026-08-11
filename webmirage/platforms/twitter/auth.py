"""Twitter cookie authentication.

Supports:
1. Environment variables: TWITTER_AUTH_TOKEN + TWITTER_CT0
2. Config file: ~/.webmirage/config.yaml
3. (Future) Browser auto-extraction via browser-cookie3
"""

from __future__ import annotations

import os
from typing import Any

from loguru import logger

from .graphql import BEARER_TOKEN_FULL
from ... import config as cfg


class AuthenticationError(Exception):
    """Raised when Twitter authentication fails."""


def get_cookies() -> dict[str, str]:
    """Get Twitter cookies from env vars or config file.

    Returns dict with keys: auth_token, ct0, cookie_string (optional).

    Raises AuthenticationError if no cookies found.
    """
    config = cfg.get_config()

    auth_token = config.get("twitter_auth_token", "")
    ct0 = config.get("twitter_ct0", "")

    # Also check raw env vars (in case config wasn't loaded yet)
    auth_token = os.environ.get("TWITTER_AUTH_TOKEN", auth_token)
    ct0 = os.environ.get("TWITTER_CT0", ct0)

    if not auth_token or not ct0:
        raise AuthenticationError(
            "Twitter cookies not found.\n"
            "Set TWITTER_AUTH_TOKEN and TWITTER_CT0 in your environment or "
            "~/.webmirage/config.yaml\n"
            "Get them from Cookie-Editor browser extension on x.com:\n"
            "  1. Login to x.com in your browser\n"
            "  2. Install Cookie-Editor Chrome extension\n"
            "  3. Click extension -> Export -> Header String\n"
            "  4. Find auth_token and ct0 values"
        )

    cookies: dict[str, str] = {
        "auth_token": auth_token,
        "ct0": ct0,
    }

    # Build a minimal cookie string for the Cookie header
    cookies["cookie_string"] = "auth_token={}; ct0={}".format(auth_token, ct0)

    logger.debug("Loaded Twitter cookies from configuration")
    return cookies


def verify_cookies(
    auth_token: str,
    ct0: str,
    cookie_string: str | None = None,
    session: Any = None,
) -> dict[str, Any]:
    """Verify cookies by calling a lightweight Twitter API endpoint.

    Only raises on clear auth failures (401/403).
    For other errors (404, network), returns empty dict.
    """
    if session is None:
        from .client import get_session

        session = get_session()

    urls = [
        "https://api.x.com/1.1/account/verify_credentials.json",
    ]

    cookie_header = cookie_string or "auth_token={}; ct0={}".format(auth_token, ct0)

    headers = {
        "Authorization": "Bearer {}".format(BEARER_TOKEN_FULL),
        "Cookie": cookie_header,
        "X-Csrf-Token": ct0,
        "X-Twitter-Active-User": "yes",
        "X-Twitter-Auth-Type": "OAuth2Session",
        "User-Agent": _get_user_agent(),
    }

    for url in urls:
        try:
            resp = session.get(url, headers=headers, timeout=5)
            if resp.status_code in (401, 403):
                raise AuthenticationError(
                    "Cookie expired or invalid (HTTP {}). "
                    "Please re-login to x.com and re-export cookies.".format(
                        resp.status_code
                    )
                )
            if resp.status_code == 200:
                data = resp.json()
                logger.info("Cookie verification succeeded: @{}", data.get("screen_name"))
                return {"screen_name": data.get("screen_name", "")}
        except AuthenticationError:
            raise
        except Exception as exc:
            logger.debug("Verification endpoint failed: {}", exc)
            continue

    logger.info("Cookie verification skipped, will verify on first API call")
    return {}


def _get_user_agent() -> str:
    """Return a Chrome-like User-Agent string."""
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
