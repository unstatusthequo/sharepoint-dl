"""Tests for sharepoint_dl.config — TOML config file persistence."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect config paths to tmp_path so tests never touch real home dir."""
    import sharepoint_dl.config as cfg

    d = tmp_path / ".sharepoint-dl"
    d.mkdir()
    monkeypatch.setattr(cfg, "CONFIG_DIR", d)
    monkeypatch.setattr(cfg, "CONFIG_PATH", d / "config.toml")
    return d


# --- load_config ---


def test_load_config_no_file_returns_defaults(config_dir: Path):
    from sharepoint_dl.config import load_config

    # Remove any file so path doesn't exist
    cfg_path = config_dir / "config.toml"
    cfg_path.unlink(missing_ok=True)

    result = load_config()
    assert result["sharepoint_url"] == ""
    assert result["download_dest"] == ""
    assert result["workers"] == 3
    assert result["flat"] is False


def test_load_config_valid_toml(config_dir: Path):
    from sharepoint_dl.config import load_config

    cfg_path = config_dir / "config.toml"
    cfg_path.write_text(
        'sharepoint_url = "https://example.sharepoint.com/sites/shared"\n'
        'download_dest = "/tmp/downloads"\n'
        "workers = 5\n"
        "flat = true\n"
    )

    result = load_config()
    assert result["sharepoint_url"] == "https://example.sharepoint.com/sites/shared"
    assert result["download_dest"] == "/tmp/downloads"
    assert result["workers"] == 5
    assert result["flat"] is True


def test_load_config_corrupt_toml_returns_defaults(config_dir: Path):
    from sharepoint_dl.config import load_config

    cfg_path = config_dir / "config.toml"
    cfg_path.write_text("this is not valid [[[ toml {{{}}}}")

    result = load_config()
    assert result["sharepoint_url"] == ""
    assert result["workers"] == 3


def test_load_config_clamps_workers(config_dir: Path):
    from sharepoint_dl.config import load_config

    cfg_path = config_dir / "config.toml"
    # Workers out of range should be clamped
    cfg_path.write_text("workers = 99\n")
    result = load_config()
    assert result["workers"] == 8

    cfg_path.write_text("workers = 0\n")
    result = load_config()
    assert result["workers"] == 1


# --- save_config ---


def test_save_config_creates_file(config_dir: Path):
    from sharepoint_dl.config import Config, save_config

    cfg: Config = {
        "sharepoint_url": "https://sp.example.com",
        "download_dest": "/data",
        "workers": 4,
        "flat": True,
    }
    save_config(cfg)
    assert (config_dir / "config.toml").exists()


def test_save_config_creates_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import sharepoint_dl.config as cfg_mod
    from sharepoint_dl.config import Config, save_config

    new_dir = tmp_path / "brand-new" / ".sharepoint-dl"
    monkeypatch.setattr(cfg_mod, "CONFIG_DIR", new_dir)
    monkeypatch.setattr(cfg_mod, "CONFIG_PATH", new_dir / "config.toml")

    config: Config = {
        "sharepoint_url": "",
        "download_dest": "",
        "workers": 3,
        "flat": False,
    }
    save_config(config)
    assert (new_dir / "config.toml").exists()


# --- round-trip ---


def test_save_then_load_roundtrip(config_dir: Path):
    from sharepoint_dl.config import Config, load_config, save_config

    original: Config = {
        "sharepoint_url": "https://contoso.sharepoint.com/sites/docs",
        "download_dest": "/Users/me/downloads",
        "workers": 6,
        "flat": True,
    }
    save_config(original)
    loaded = load_config()
    assert loaded == original


# --- merge_config ---


def test_merge_config_overrides():
    from sharepoint_dl.config import Config, merge_config

    base: Config = {
        "sharepoint_url": "https://base.example.com",
        "download_dest": "/base",
        "workers": 2,
        "flat": False,
    }
    result = merge_config(base, workers=4)
    assert result["workers"] == 4
    # Unchanged fields preserved
    assert result["sharepoint_url"] == "https://base.example.com"
    assert result["flat"] is False


def test_merge_config_none_overrides_ignored():
    from sharepoint_dl.config import Config, merge_config

    base: Config = {
        "sharepoint_url": "https://base.example.com",
        "download_dest": "/base",
        "workers": 2,
        "flat": False,
    }
    result = merge_config(base, workers=None, flat=None)
    assert result["workers"] == 2
    assert result["flat"] is False
