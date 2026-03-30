---
created: "2026-03-30T18:18:24.263Z"
title: Timestamped log file for audit trail
area: general
priority: low
files:
  - sharepoint_dl/downloader/engine.py
  - sharepoint_dl/cli/main.py
---

## Problem

The tool prints status to the console but doesn't persist a log. For forensic use cases, having a timestamped record of every action (auth events, enumeration results, download starts/completions, errors, retries) is valuable for audit trails and debugging.

## Solution

Write a `download.log` file in the destination directory alongside state.json and manifest.json. Use Python logging with timestamps. Log: auth events, enumeration count, each file start/complete/fail with timestamps, retry attempts, final completeness report. Human-readable format.
