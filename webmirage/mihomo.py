"""Small, secret-safe client for the Mihomo external controller."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class MihomoControllerError(RuntimeError):
    """Raised when the Mihomo controller cannot complete a request."""


@dataclass(frozen=True)
class MihomoController:
    """Minimal client for the controller endpoints WebMirage needs."""
    base_url: str
    secret: str
    timeout: float = 8.0

    def _request(self, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self.secret:
            headers["Authorization"] = f"Bearer {self.secret}"
        request = Request(f"{self.base_url.rstrip('/')}{path}", data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise MihomoControllerError("controller authentication failed") from exc
            raise MihomoControllerError(f"controller returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise MihomoControllerError(f"controller unavailable: {exc.reason}") from exc
        except TimeoutError as exc:
            raise MihomoControllerError("controller request timed out") from exc
        try:
            decoded = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise MihomoControllerError("controller returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise MihomoControllerError("controller returned an unexpected response")
        return decoded

    def status(self) -> dict[str, Any]:
        version = self._request("/version")
        proxies = self._request("/proxies").get("proxies", {})
        if not isinstance(proxies, dict):
            raise MihomoControllerError("controller returned invalid proxy data")
        groups: list[dict[str, Any]] = []
        for name, detail in proxies.items():
            if not isinstance(name, str) or not isinstance(detail, dict):
                continue
            if detail.get("type") not in {"Selector", "URLTest", "Fallback", "LoadBalance"}:
                continue
            candidates = detail.get("all", [])
            groups.append({"name": name, "type": detail.get("type", "unknown"), "selected": detail.get("now", ""), "candidates": [item for item in candidates if isinstance(item, str)]})
        return {"version": version.get("version", "unknown"), "groups": groups}

    def select_proxy(self, group: str, node: str) -> None:
        _validate_proxy_name("group", group)
        _validate_proxy_name("node", node)
        self._request("/proxies/" + quote(group, safe=""), method="PUT", payload={"name": node})


def _validate_proxy_name(label: str, value: str) -> None:
    if not value or len(value) > 200 or any(ord(char) < 32 for char in value):
        raise MihomoControllerError(f"invalid proxy {label}")
