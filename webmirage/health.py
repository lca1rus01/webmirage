"""In-memory per-platform health tracking.

Records the outcome of every tool call (success / failure + timestamp)
so the ``webmirage_health`` tool can report which platforms are actually
working and which ones have stale credentials.

Records live only for the lifetime of the server process — that is
intentional: health describes *recent* traffic, not history.
"""

from __future__ import annotations

import time
from typing import Any

_RECORDS: dict[str, dict[str, Any]] = {}


def record(platform: str, ok: bool, detail: str = "") -> None:
    """Record one tool-call outcome for a platform."""
    now = time.time()
    rec = _RECORDS.setdefault(platform, {"calls": 0, "ok": 0, "fail": 0})
    rec["calls"] += 1
    if ok:
        rec["ok"] += 1
        rec["last_success"] = now
        rec.pop("last_error_msg", None)
    else:
        rec["fail"] += 1
        rec["last_error"] = now
        rec["last_error_msg"] = (detail or "")[:200]


def _fmt_age(ts: float | None) -> str:
    """Format a unix timestamp as a human-relative age."""
    if ts is None:
        return "never"
    delta = max(0, time.time() - ts)
    if delta < 60:
        return "{}s ago".format(int(delta))
    if delta < 3600:
        return "{}m ago".format(int(delta // 60))
    if delta < 86400:
        return "{}h ago".format(int(delta // 3600))
    return "{:.1f}d ago".format(delta / 86400)


def snapshot() -> dict[str, dict[str, Any]]:
    """Return a copy of health records for reporting."""
    return {
        name: {
            "calls": rec["calls"],
            "ok": rec["ok"],
            "fail": rec["fail"],
            "last_success": _fmt_age(rec.get("last_success")),
            "last_error": _fmt_age(rec.get("last_error")),
            "last_error_msg": rec.get("last_error_msg", ""),
        }
        for name, rec in _RECORDS.items()
    }


def looks_like_error(text: str) -> bool:
    """Heuristic: does a tool result look like a failure?

    Platform clients report soft failures as plain text (no exception),
    e.g. "Xueqiu API error: ..." or "闲鱼接口异常: ...", so we sniff the
    head of the result for known error markers.
    """
    head = text[:200].lstrip().lower()
    if head.startswith("error"):
        return True
    if " api error" in head:
        return True
    if "接口异常" in text[:200] or "接口打开" in text[:200]:
        return True
    return False
