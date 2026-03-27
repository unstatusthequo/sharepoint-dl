# Phase 05 Research: Manifest Path Accuracy

**Date:** 2026-03-27
**Question:** What do we need to know to plan Phase 05 well?

## Recommended Approach

- Use persisted `state["local_path"]` as the primary source of truth for manifest `local_path`.
- Do not keep deriving manifest paths from `folder_path + "/" + name`; that is the current bug.
- Do not use `_local_path(...)` as the manifest's primary source either; recomputation is weaker than persisted state.
- Add one shared relative-path fallback helper for legacy entries that have no `local_path`.
- Pass `flat` into manifest generation from the CLI so legacy flat entries can be backfilled correctly.
- Keep manifest `local_path` relative to `dest_dir`, not absolute.

## Key Risks

- Legacy state entries created before Phase 04 can still have no `local_path`.
- Legacy flat runs cannot be inferred from remote metadata alone without the current `flat` mode.
- Stored `local_path` should be validated defensively; do not trust absolute paths or `..` traversal.
- Flat duplicate filenames remain a separate risk, but that is outside this phase.

## Concrete Files

Required:
- `sharepoint_dl/manifest/writer.py`
- `sharepoint_dl/cli/main.py`
- `tests/test_manifest.py`
- `tests/test_cli.py`

Recommended for a cleaner single source of truth:
- `sharepoint_dl/downloader/engine.py`
- `sharepoint_dl/state/job_state.py`
- or a small shared path helper module

## Suggested Split

One plan is enough:
1. source-of-truth and fallback wiring
2. CLI `flat` propagation
3. regression tests

## Verification Strategy

- Add manifest tests that assert actual `local_path` values, not just field presence.
- Cover:
  - preserved-folder mode with stored `local_path`
  - flat mode with stored `local_path`
  - legacy preserved-folder fallback when `local_path` is missing
  - legacy flat fallback when `local_path` is missing and `flat=True`
  - stored `local_path` winning over fallback
- Add CLI integration coverage for auth-expired partial runs in both normal and flat mode, asserting `manifest.json` contains the expected `local_path`.
