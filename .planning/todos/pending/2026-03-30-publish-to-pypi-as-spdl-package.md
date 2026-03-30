---
created: "2026-03-30T18:18:24.263Z"
title: Publish to PyPI as spdl package
area: tooling
priority: high
files:
  - pyproject.toml
  - setup.sh
  - setup.ps1
---

## Problem

Currently users must clone the repo and run setup scripts. This is a barrier for non-technical users and makes distribution harder. For a public release, `pip install spdl` is the expected experience.

## Solution

Publish to PyPI as `spdl`. Users install with `pip install spdl` or `uv tool install spdl`, then run `spdl` from anywhere. Requires: choosing a non-conflicting package name, adding classifiers/license to pyproject.toml, setting up PyPI publishing (GitHub Actions or manual twine upload), and post-install Playwright chromium setup guidance.
