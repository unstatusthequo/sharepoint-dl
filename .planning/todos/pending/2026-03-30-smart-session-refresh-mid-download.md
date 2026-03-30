---
created: "2026-03-30T18:18:24.263Z"
title: Smart session refresh mid-download
area: auth
priority: medium
files:
  - sharepoint_dl/downloader/engine.py
  - sharepoint_dl/auth/browser.py
---

## Problem

When the session expires mid-download (401/403), the tool halts all workers and tells the user to re-run. This means the user has to manually re-authenticate and restart, even though completed files are preserved. For 237 GB downloads that take hours, session expiry is expected — the current UX makes it painful.

## Solution

On 401/403, pause workers, automatically re-open the browser for re-auth, capture new cookies, inject into the session, and resume downloads. No re-run needed, no lost progress, seamless experience.
