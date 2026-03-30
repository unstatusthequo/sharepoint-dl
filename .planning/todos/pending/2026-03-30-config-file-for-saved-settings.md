---
created: "2026-03-30T18:18:24.263Z"
title: Config file for saved settings
area: general
priority: low
files:
  - sharepoint_dl/cli/main.py
---

## Problem

Users re-enter the same SharePoint URL, download destination, and worker count every time they run the tool. For repeat users downloading from the same SharePoint site, this is unnecessary friction.

## Solution

Save frequently-used settings to `~/.sharepoint-dl/config.json`: default SharePoint URL, default destination directory, default worker count, saved folder bookmarks. Interactive mode pre-fills from config. CLI mode uses config as defaults.
