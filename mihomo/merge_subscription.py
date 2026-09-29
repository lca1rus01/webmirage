#!/usr/bin/env python3
"""Merge a Mihomo subscription into a validated WebMirage-owned config."""
from __future__ import annotations
import argparse
import re
from pathlib import Path
from typing import Any
import yaml

_SHORT_ID_RE = re.compile(r"^[0-9a-fA-F]{1,16}$")

def normalize_short_ids(value: Any) -> None:
    """Normalize REALITY short IDs; Mihomo requires even-length hexadecimal strings."""
    if isinstance(value, dict):
        if "short-id" in value and value["short-id"] not in (None, ""):
            short_id = str(value["short-id"]).strip()
            if not _SHORT_ID_RE.fullmatch(short_id):
                raise ValueError(f"invalid REALITY short-id: {short_id!r}")
            value["short-id"] = ("0" + short_id if len(short_id) % 2 else short_id).lower()
        for child in value.values(): normalize_short_ids(child)
    elif isinstance(value, list):
        for child in value: normalize_short_ids(child)

def merge(subscription: Path, output: Path, secret_file: Path) -> None:
    data = yaml.safe_load(subscription.read_text(encoding="utf-8"))
    if not isinstance(data, dict): raise ValueError("subscription root must be a YAML mapping")
    if not isinstance(data.get("proxies"), list) or not data["proxies"]: raise ValueError("subscription contains no proxies")
    secret = secret_file.read_text(encoding="utf-8").strip() if secret_file.exists() else ""
    if not secret: raise ValueError("controller secret file is missing or empty")
    normalize_short_ids(data)
    data.update({"allow-lan": True, "log-level": "info", "external-controller": "0.0.0.0:9090", "secret": secret})
    data.pop("redir-port", None)
    rules = data.get("rules", [])
    if not isinstance(rules, list): raise ValueError("subscription rules must be a list")
    lan = ["IP-CIDR,10.0.0.0/8,DIRECT,no-resolve", "IP-CIDR,172.16.0.0/12,DIRECT,no-resolve", "IP-CIDR,192.168.0.0/16,DIRECT,no-resolve"]
    cn = ["GEOSITE,cn,DIRECT", "GEOIP,CN,DIRECT,no-resolve"]
    matches = [rule for rule in rules if str(rule).startswith("MATCH")]
    data["rules"] = lan + [rule for rule in rules if not str(rule).startswith("MATCH")] + cn + (matches[-1:] or ["MATCH,Proxy"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=4096), encoding="utf-8")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subscription", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--secret-file", type=Path, required=True)
    args = parser.parse_args(); merge(args.subscription, args.output, args.secret_file)
if __name__ == "__main__": main()
