---
created: "2026-03-30T18:18:24.263Z"
title: Auto-detect root folder from sharing link
area: general
priority: high
files:
  - sharepoint_dl/cli/main.py
---

## Problem

CLI mode requires `-r` with a long server-relative path (e.g., `/sites/Team/Shared Documents/General/EDiscovery Data/Images`). This is the hardest part of using the tool — users must manually extract the `id=` parameter from the browser URL. The interactive mode already resolves this by following the sharing link redirect, but CLI mode doesn't.

## Solution

Follow the sharing link redirect in CLI mode too. Extract the `id=` parameter from the final URL automatically. Make `-r` optional — auto-detect when possible, require it only as a fallback.
