# Coding Conventions

**Analysis Date:** 2026-03-30

## Naming Patterns

**Files:**
- Python modules use `snake_case.py` throughout, including `sharepoint_dl/cli/main.py`, `sharepoint_dl/downloader/engine.py`, and `sharepoint_dl/state/job_state.py`.
- Test files live under `tests/` and use `test_*.py` naming, such as `tests/test_cli.py` and `tests/test_downloader.py`.
- Package entrypoints are kept explicit rather than hidden behind deep indirection; `sharepoint_dl/__main__.py` and `sharepoint_dl/cli/main.py` are the primary CLI surfaces.

**Functions:**
- Functions use `snake_case` consistently, including private helpers like `_build_download_url()` and `_resolve_folder_from_browser_url()`.
- Async-specific prefixes are not used because the codebase is synchronous.
- Helpers with internal scope are commonly prefixed with `_`, especially in `sharepoint_dl/cli/main.py` and `sharepoint_dl/downloader/engine.py`.

**Variables:**
- Local variables are `snake_case`, including descriptive names like `server_relative_url`, `download_url`, and `part_path`.
- Constants use `UPPER_SNAKE_CASE`, such as `CHUNK_SIZE` in `sharepoint_dl/downloader/engine.py` and `SESSION_DIR` in `sharepoint_dl/auth/session.py`.
- Private state is not marked with special suffixes or prefixes beyond module-private naming conventions.

**Types:**
- Classes and dataclasses use `PascalCase`, such as `FileEntry`, `FileStatus`, and `JobState`.
- Enum values use `UPPER_SNAKE_CASE` members with string values, as in `FileStatus.PENDING` and `FileStatus.COMPLETE`.
- Type annotations are used heavily, including explicit return types on helpers and container types like `list[FileEntry]` and `dict[str, dict]`.

## Code Style

**Formatting:**
- The project uses Ruff for linting/formatting conventions via `pyproject.toml`.
- Line length is set to 100 characters in `[tool.ruff]`.
- Strings are mostly double-quoted in the source files.
- Modules use `from __future__ import annotations` to keep annotations lightweight and forward-reference friendly.

**Linting:**
- Ruff is the only explicit formatter/linter configuration in `pyproject.toml`.
- There is no separate `ruff.toml`, so the repo relies on project-level config.
- The code follows a clean, direct style with minimal abstraction and very little inline cleverness.

## Import Organization

**Order:**
1. Standard library imports, often grouped by module family.
2. Third-party imports like `requests`, `typer`, `rich`, and `tenacity`.
3. Local application imports from `sharepoint_dl.*`.
4. Type-only imports are guarded with `TYPE_CHECKING` where needed, as in `sharepoint_dl/downloader/engine.py` and `sharepoint_dl/state/job_state.py`.

**Grouping:**
- Imports are grouped with blank lines between standard library, third-party, and local imports.
- In larger modules, related imports are clustered rather than alphabetized aggressively.

**Path Aliases:**
- No path aliases are defined.
- Imports are package-relative through `sharepoint_dl.*`.

## Error Handling

**Patterns:**
- The code prefers explicit exceptions over sentinel returns when a failure should stop the flow.
- Auth failures raise `AuthExpiredError` in `sharepoint_dl/enumerator/traversal.py` and `sharepoint_dl/downloader/engine.py`.
- External-call boundaries use `try/except` sparingly and return a conservative fallback when recovery is better than bubbling, such as `validate_session()` returning `False` on `requests.RequestException`.

**Error Types:**
- `AuthExpiredError` is the primary domain error for expired SharePoint sessions.
- `ValueError` is used for local integrity failures like size mismatch in `_download_file()`.
- `requests.HTTPError` is allowed to propagate through retry wrappers when the failure is retryable.

## Logging

**Framework:**
- Standard-library `logging` is used, with module loggers created via `logging.getLogger(__name__)`.
- Logging is wired into tenacity retry hooks through `before_sleep_log`.

**Patterns:**
- Logging is concentrated around external-call and retry boundaries, not inside pure helpers.
- The downloader and enumerator modules log retry behavior rather than every internal state transition.
- There is no custom structured logging framework beyond standard logger usage.

## Comments

**When to Comment:**
- Comments explain why a choice exists, not what a line obviously does.
- Several comments call out operationally important decisions, such as using `download.aspx` instead of `/$value` in `sharepoint_dl/downloader/engine.py`.
- Comments are used to explain retry/auth behavior and atomic write assumptions where the code would otherwise be opaque.

**JSDoc/TSDoc:**
- Public and semi-public functions are documented with docstrings.
- Docstrings usually include Args/Returns/Raises when the function has non-trivial behavior.
- Short internal helpers still get docstrings when the purpose is not obvious.

**TODO Comments:**
- No persistent TODO convention is visible in the checked-in code.
- The repo does not rely on username-tagged TODO comments.

## Function Design

**Size:**
- Functions are kept small and direct.
- Larger behaviors are decomposed into narrowly scoped helpers, for example the CLI splitting URL resolution, folder listing, and interactive flow into separate functions in `sharepoint_dl/cli/main.py`.

**Parameters:**
- Parameter lists are usually explicit and readable.
- Functions that take more context use named parameters rather than positional compression, for example `_download_file(session, file_entry, dest_path, site_url, on_chunk=None)`.

**Return Values:**
- Functions tend to return concrete values instead of mutating hidden globals.
- Early returns are common for guards and simple fallbacks.
- Single-purpose helpers often return `Path`, `bool`, `str`, or small tuples.

## Module Design

**Exports:**
- Named module functions and classes are preferred over dynamic export patterns.
- `__init__.py` files exist for package wiring, but the implementation lives in the functional modules.

**Barrel Files:**
- Barrel-style re-exporting is limited.
- The code favors direct imports from the owning module, such as `from sharepoint_dl.downloader.engine import download_all`.

---

*Convention analysis: 2026-03-30*
*Update when patterns change*
