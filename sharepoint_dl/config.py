"""Config file persistence — load/save TOML from ~/.sharepoint-dl/config.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TypedDict

import tomli_w

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class Config(TypedDict):
    sharepoint_url: str
    download_dest: str
    workers: int
    flat: bool


# ---------------------------------------------------------------------------
# Paths & defaults
# ---------------------------------------------------------------------------

CONFIG_DIR: Path = Path.home() / ".sharepoint-dl"
CONFIG_PATH: Path = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG: Config = {
    "sharepoint_url": "",
    "download_dest": "",
    "workers": 3,
    "flat": False,
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config() -> Config:
    """Load config from disk. Returns defaults on missing/corrupt file."""
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)  # type: ignore[return-value]

    try:
        raw = CONFIG_PATH.read_text(encoding="utf-8")
        data = tomllib.loads(raw)
    except Exception:
        return dict(DEFAULT_CONFIG)  # type: ignore[return-value]

    return _validate(data)


def save_config(config: Config) -> None:
    """Write config to disk atomically (write .tmp, then rename)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".toml.tmp")
    tmp.write_bytes(tomli_w.dumps(dict(config)).encode("utf-8"))
    tmp.rename(CONFIG_PATH)


def merge_config(config: Config, **overrides: object) -> Config:
    """Return new Config with non-None overrides replacing config values."""
    merged = dict(config)
    for key, value in overrides.items():
        if value is not None and key in merged:
            merged[key] = value
    return merged  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate(data: dict) -> Config:  # type: ignore[type-arg]
    """Coerce raw TOML dict into a valid Config, falling back to defaults."""
    result = dict(DEFAULT_CONFIG)  # type: ignore[assignment]

    if isinstance(data.get("sharepoint_url"), str):
        result["sharepoint_url"] = data["sharepoint_url"]

    if isinstance(data.get("download_dest"), str):
        result["download_dest"] = data["download_dest"]

    if isinstance(data.get("workers"), int):
        result["workers"] = max(1, min(8, data["workers"]))

    if isinstance(data.get("flat"), bool):
        result["flat"] = data["flat"]

    return result  # type: ignore[return-value]
