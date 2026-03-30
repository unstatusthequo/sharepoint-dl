---
created: "2026-03-30T18:18:24.263Z"
title: Multi-folder batch download mode
area: general
priority: high
files:
  - sharepoint_dl/cli/main.py
  - sharepoint_dl/downloader/engine.py
---

## Problem

Users with multiple custodians (e.g., 3+ forensic image sets) must run the tool separately for each folder. Each run requires re-entering the URL and navigating the folder tree. With large evidence collections this is tedious and error-prone.

## Solution

In interactive mode: after selecting a folder, offer "Add another folder?" before starting downloads. Queue multiple folders, one auth session, sequential or parallel execution. Each folder gets its own state.json and manifest.json in its destination.
