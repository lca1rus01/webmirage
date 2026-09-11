"""Small GitHub REST API client used by the GitHub MCP tools."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from loguru import logger

_API_ROOT = "https://api.github.com"
_TIMEOUT = 15
_MAX_RETRIES = 3
_MAX_BACKOFF = 120


class GitHubError(Exception):
    """Raised when GitHub cannot satisfy a request."""


class GitHubClient:
    """Thread-safe, token-aware GitHub REST API client."""

    def __init__(self, tokens: list[str] | None = None) -> None:
        self._tokens = list(dict.fromkeys(token for token in (tokens or []) if token))
        self._token_index = 0
        self._rate_limited: set[int] = set()
        self._etag_cache: dict[str, tuple[str, Any]] = {}
        self._lock = threading.Lock()

    @property
    def authenticated(self) -> bool:
        return bool(self._tokens)

    def _token_for_request(self) -> tuple[int, str]:
        with self._lock:
            if not self._tokens:
                return -1, ""
            available = [
                index for index in range(len(self._tokens))
                if index not in self._rate_limited
            ]
            if not available:
                self._rate_limited.clear()
                available = list(range(len(self._tokens)))
            index = available[self._token_index % len(available)]
            self._token_index = (self._token_index + 1) % len(available)
            return index, self._tokens[index]

    def _mark_rate_limited(self, token_index: int) -> None:
        if token_index >= 0:
            with self._lock:
                self._rate_limited.add(token_index)

    @staticmethod
    def _retry_after(headers: Any) -> float:
        reset = headers.get("X-RateLimit-Reset")
        if reset:
            try:
                return min(
                    max(float(reset) - time.time() + 2, 5),
                    _MAX_BACKOFF,
                )
            except ValueError:
                pass
        retry_after = headers.get("Retry-After")
        try:
            return min(max(float(retry_after), 5), _MAX_BACKOFF) if retry_after else 5
        except ValueError:
            return 5

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET a GitHub API path with retries, pagination support in callers, and ETags."""
        query = urllib.parse.urlencode(
            [(key, value) for key, value in (params or {}).items() if value is not None]
        )
        url = path if path.startswith("http") else _API_ROOT + path
        if query:
            url += "?" + query
        cached = self._etag_cache.get(url)

        last_error = "GitHub request failed"
        for attempt in range(_MAX_RETRIES * max(len(self._tokens), 1)):
            token_index, token = self._token_for_request()
            headers = {
                "Accept": "application/vnd.github+json",
                "User-Agent": "webmirage-github",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if token:
                headers["Authorization"] = "Bearer " + token
            if cached:
                headers["If-None-Match"] = cached[0]
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    etag = response.headers.get("ETag")
                    if etag:
                        self._etag_cache[url] = (etag, payload)
                    return payload
            except urllib.error.HTTPError as exc:
                last_error = self._error_message(exc)
                if exc.code == 304 and cached:
                    return cached[1]
                if exc.code in (403, 429):
                    self._mark_rate_limited(token_index)
                    wait = self._retry_after(exc.headers)
                    logger.warning("GitHub rate limited; retrying in {:.1f}s", wait)
                    time.sleep(wait)
                    continue
                if exc.code == 404:
                    raise GitHubError("GitHub resource not found: {}".format(path)) from exc
                if exc.code == 422:
                    raise GitHubError("GitHub rejected the request: {}".format(last_error)) from exc
                if 500 <= exc.code < 600:
                    time.sleep(2)
                    continue
                raise GitHubError(last_error) from exc
            except (TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
                last_error = str(exc)
                if attempt + 1 < _MAX_RETRIES * max(len(self._tokens), 1):
                    time.sleep(2)
                    continue
                raise GitHubError("GitHub network error: {}".format(last_error)) from exc
        raise GitHubError(last_error)

    @staticmethod
    def _error_message(exc: urllib.error.HTTPError) -> str:
        try:
            body = json.loads(exc.read().decode("utf-8"))
            message = body.get("message")
            if message:
                return "HTTP {}: {}".format(exc.code, message)
        except (UnicodeDecodeError, json.JSONDecodeError, OSError):
            pass
        return "HTTP {}".format(exc.code)

    def search_repositories(self, query: str, **params: Any) -> dict[str, Any]:
        return self.get("/search/repositories", {"q": query, **params})

    def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        return self.get("/repos/{}/{}".format(owner, repo))

    def get_readme(self, owner: str, repo: str) -> dict[str, Any]:
        return self.get("/repos/{}/{}/readme".format(owner, repo))

    def get_issues(self, owner: str, repo: str, **params: Any) -> list[dict[str, Any]]:
        return self.get("/repos/{}/{}/issues".format(owner, repo), params)

    def get_issue(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        return self.get("/repos/{}/{}/issues/{}".format(owner, repo, number))

    def get_releases(self, owner: str, repo: str, **params: Any) -> list[dict[str, Any]]:
        return self.get("/repos/{}/{}/releases".format(owner, repo), params)

    def get_pull_requests(self, owner: str, repo: str, **params: Any) -> list[dict[str, Any]]:
        return self.get("/repos/{}/{}/pulls".format(owner, repo), params)
