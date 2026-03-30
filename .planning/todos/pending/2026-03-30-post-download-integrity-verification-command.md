---
created: "2026-03-30T18:18:24.263Z"
title: Post-download integrity verification command
area: general
priority: high
files:
  - sharepoint_dl/cli/main.py
  - sharepoint_dl/manifest/writer.py
---

## Problem

The manifest records SHA-256 hashes computed during download, but there's no way to verify files haven't been corrupted after download (disk errors, accidental modification, transfer to another machine). For forensic chain of custody, you need to prove the files on disk right now match what was originally downloaded.

## Solution

Add a `verify` command that reads each file from disk, recomputes SHA-256, and compares against manifest.json. Reports any mismatches. Critical for forensic use — proves integrity at any point after download, not just at download time.
