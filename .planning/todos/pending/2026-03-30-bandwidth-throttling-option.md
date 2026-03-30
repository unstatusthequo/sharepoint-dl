---
created: "2026-03-30T18:18:24.263Z"
title: Bandwidth throttling option
area: general
priority: medium
files:
  - sharepoint_dl/downloader/engine.py
  - sharepoint_dl/cli/main.py
---

## Problem

Downloading hundreds of GB saturates the network connection, affecting other users and services on the same network. Especially problematic on shared corporate connections or VPNs.

## Solution

Add `--throttle 50MB/s` flag that rate-limits total download bandwidth across all workers. Implement via token bucket or sleep-between-chunks approach. Default: unlimited.
