# Milestones

## v1.1 Feature Expansion (Shipped: 2026-04-01)

**Phases completed:** 4 phases, 9 plans, 13 tasks

**Key accomplishments:**

- Rich progress bar with ETA/speed display and file-only timestamped download.log for post-run audit
- --root-folder now optional on download/list commands; sharing link URL auto-resolves to server-relative folder path via extracted resolve.py module
- TOML config persistence with load/save/merge and thread-safe token bucket bandwidth throttle with CLI parser
- verify command re-hashes downloaded files via SHA-256, --throttle flag creates shared TokenBucket, config pre-fills prompts and saves after successful download
- ReauthController with check-lock-check pattern using threading.Lock + threading.Event, cookies updated in-place on shared session, max 3 attempts enforced, Playwright dependency isolated in browser.py
- engine.py changes:
- `_job_dest(batch_root, folder_path) -> Path`
- TUI startup menu with Download/Verify options and throttle prompt with config persistence using parse_throttle() validation loop

---
