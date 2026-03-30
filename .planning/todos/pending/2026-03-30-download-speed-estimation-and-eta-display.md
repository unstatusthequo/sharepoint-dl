---
created: "2026-03-30T18:18:24.263Z"
title: Download speed estimation and ETA display
area: general
priority: medium
files:
  - sharepoint_dl/downloader/engine.py
---

## Problem

When downloading 237 GB across 165 files, users have no idea when the download will finish. The progress bar shows bytes transferred but not estimated time remaining. For multi-hour downloads, knowing the ETA matters for planning.

## Solution

Add a rolling-average speed calculation and ETA to the overall progress bar. Display like: "142.3 GB / 237.1 GB — 45.2 MB/s — ~35m remaining". Rich Progress supports TimeRemainingColumn natively.
