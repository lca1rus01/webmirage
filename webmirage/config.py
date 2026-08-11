"""Configuration management for webmirage.

Priority: environment variables > config file > defaults.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

CONFIG_DIR = Path.home() / ".webmirage"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


def _load_dotenv() -> None:
    """Load .env file from CWD if python-dotenv is available."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        # Manual fallback: read .env if present
        env_path = Path.cwd() / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip("\"'")
                if key and key not in os.environ:
                    os.environ[key] = value


def _load_config_file() -> dict[str, Any]:
    """Load YAML config from ~/.webmirage/config.yaml."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        return yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("Failed to read config file {}: {}", CONFIG_FILE, exc)
        return {}


_config_cache: dict[str, Any] | None = None


def get_config() -> dict[str, Any]:
    """Get merged config: defaults < config file < env vars."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    _load_dotenv()
    file_config = _load_config_file()

    # Build merged config
    config: dict[str, Any] = {}

    # Twitter config
    config["twitter_auth_token"] = os.environ.get(
        "TWITTER_AUTH_TOKEN", file_config.get("twitter_auth_token", "")
    )
    config["twitter_ct0"] = os.environ.get(
        "TWITTER_CT0", file_config.get("twitter_ct0", "")
    )
    config["twitter_proxy"] = os.environ.get(
        "TWITTER_PROXY", file_config.get("twitter_proxy", "")
    )

    # Rate limit defaults
    config["request_delay"] = file_config.get("request_delay", 2.5)
    config["max_retries"] = file_config.get("max_retries", 3)
    config["max_count"] = file_config.get("max_count", 50)

    # Twitter watchlist — list of screen names to monitor
    config["twitter_watchlist"] = file_config.get("twitter_watchlist", [])

    # Xueqiu config
    config["xueqiu_cookie"] = os.environ.get(
        "XUEQIU_COOKIE", file_config.get("xueqiu_cookie", "")
    )
    config["xueqiu_watchlist"] = file_config.get("xueqiu_watchlist", [])

    # Xianyu (闲鱼/Goofish) config
    # cookie 必须包含 _m_h5_tk(签名token) 与 unb(用户ID)；user_id 可省略，
    # 省略时 client 会自动从 cookie 的 unb 字段解析。
    config["xianyu_cookie"] = os.environ.get(
        "XIANYU_COOKIE", file_config.get("xianyu_cookie", "")
    )
    config["xianyu_user_id"] = os.environ.get(
        "XIANYU_USER_ID", file_config.get("xianyu_user_id", "")
    )

    _config_cache = config
    return config


def save_config(updates: dict[str, Any]) -> None:
    """Persist config updates to ~/.webmirage/config.yaml."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    current = _load_config_file()
    current.update(updates)
    CONFIG_FILE.write_text(yaml.safe_dump(current, allow_unicode=True), encoding="utf-8")
    # Invalidate cache
    global _config_cache
    _config_cache = None
    logger.info("Config saved to {}", CONFIG_FILE)


def is_twitter_configured() -> bool:
    """Check if Twitter credentials are available."""
    cfg = get_config()
    return bool(cfg.get("twitter_auth_token") and cfg.get("twitter_ct0"))
