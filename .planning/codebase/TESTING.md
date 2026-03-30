# Testing Patterns

**Analysis Date:** 2026-03-30

## Test Framework

**Runner:**
- `pytest` is the project test runner, configured in `pyproject.toml` with `testpaths = ["tests"]`.
- Test files are located under the top-level `tests/` directory, not inside the package.

**Assertion Library:**
- Tests use `pytest` assertions plus standard `pytest.raises`.
- Mock objects come from `unittest.mock`, not a separate assertion library.

**Run Commands:**
```bash
uv run pytest                       # Run all tests
uv run pytest tests/test_cli.py     # Single file
uv run pytest -q                    # Quiet mode
uv run pytest --maxfail=1           # Stop after first failure
```

## Test File Organization

**Location:**
- All tests live in `tests/`.
- There is no `src/` tree or colocated `*.test.py` layout.

**Naming:**
- Files follow `test_<module>.py`, such as `tests/test_auth.py`, `tests/test_manifest.py`, and `tests/test_state.py`.
- The test suite is organized by module boundary rather than by feature area.

**Structure:**
```
tests/
  conftest.py
  test_auth.py
  test_cli.py
  test_downloader.py
  test_manifest.py
  test_state.py
  test_traversal.py
```

## Test Structure

**Suite Organization:**
```python
from unittest.mock import MagicMock, patch

class TestDownloadCommand:
    def test_download_calls_with_correct_args(self):
        mock_session = MagicMock()
        with patch("sharepoint_dl.cli.main.load_session", return_value=mock_session):
            result = runner.invoke(app, ["download", TEST_URL, "/tmp/dest", "--yes"])
        assert result.exit_code == 0
```

**Patterns:**
- Tests are grouped into `Test*` classes with focused method names.
- Shared setup lives in fixtures inside `tests/conftest.py`.
- Per-test setup is preferred over broad `beforeAll`-style fixtures.
- Tests usually follow an arrange/act/assert shape, often with inline comments when the flow is non-obvious.

## Mocking

**Framework:**
- `unittest.mock.MagicMock` and `unittest.mock.patch` are the dominant mocking tools.
- Patching is done at the import boundary of the module under test, for example `patch("sharepoint_dl.cli.main.download_all")`.

**Patterns:**
```python
@patch("sharepoint_dl.cli.main.load_session")
@patch("sharepoint_dl.cli.main.validate_session")
def test_list_no_session(self, mock_validate, mock_load):
    mock_load.return_value = None
    result = runner.invoke(app, ["list", TEST_URL, "--root-folder", "/sites/shared/Images"])
    assert result.exit_code == 1
```

**What to Mock:**
- Browser automation in `sharepoint_dl.auth.browser`.
- Network and requests-layer calls in CLI and downloader tests.
- Progress UI objects and other side-effect-heavy boundaries.

**What NOT to Mock:**
- Pure helper behavior such as path derivation and simple state transitions when they can be tested directly.
- Internal value objects like `FileEntry` when the test can instantiate them cheaply.

## Fixtures and Factories

**Test Data:**
```python
@pytest.fixture
def file_entries() -> list[FileEntry]:
    return [
        FileEntry(name="evidence_001.E01", server_relative_url="/a/file1", size_bytes=100, folder_path="/a"),
    ]
```

**Location:**
- Shared fixtures live in `tests/conftest.py`.
- Factories are often lightweight fixture functions instead of separate factory modules.
- Mock response factories are used for download behavior, such as `mock_download_response` in `tests/conftest.py`.

## Coverage

**Requirements:**
- No coverage threshold is defined in `pyproject.toml`.
- Coverage appears to be informational rather than enforced.

**Configuration:**
- No explicit coverage plugin configuration is present.
- `pytest` is the only test tooling configured in the repository metadata.

**View Coverage:**
```bash
uv run pytest --cov
```

## Test Types

**Unit Tests:**
- Most tests are unit tests over isolated functions or modules.
- External systems are mocked aggressively so tests stay deterministic.

**Integration Tests:**
- The current tree does not show a separate integration test directory.
- Module-level tests still exercise real internal logic through public helpers where feasible.

**E2E Tests:**
- No dedicated E2E framework is configured in the repo.
- CLI tests in `tests/test_cli.py` are the closest thing to end-to-end coverage, but they still rely on mocks.

## Common Patterns

**Async Testing:**
- Not applicable; the codebase is synchronous.

**Error Testing:**
```python
with pytest.raises(ValueError, match="Size mismatch"):
    _download_file(session, sample_entry, dest, site_url)

assert session.get.call_count == 1
```
- Tests assert both the raised exception and the side effect count when retries or failure modes matter.

**Snapshot Testing:**
- Snapshot testing is not used.
- Assertions are explicit on output, return values, and call counts instead.

---

*Testing analysis: 2026-03-30*
*Update when test patterns change*
