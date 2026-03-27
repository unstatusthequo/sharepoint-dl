# Pitfalls Research

**Domain:** SharePoint bulk file downloader — guest/external auth, large file downloads, forensic integrity
**Researched:** 2026-03-27
**Confidence:** HIGH (most pitfalls verified against official Microsoft docs and confirmed GitHub issues)

---

## Critical Pitfalls

### Pitfall 1: SharePoint REST API Pagination Silently Truncates Results

**What goes wrong:**
The most likely cause of the prior Python script silently skipping files. When using `GetFolderByServerRelativeUrl(...)/Files`, SharePoint defaults to returning the first 100 items with no automatic continuation. If the code iterates what it received without checking for a `@odata.nextLink` or `skiptoken`, it processes a partial list and never knows it stopped early. No error is raised. Files beyond position 100 simply never appear.

**Why it happens:**
Developers assume `GET /Files` returns all files. SharePoint's REST API uses opaque `$skiptoken` pagination, not simple `$skip` offset. The `$skip` parameter does not work correctly on Files endpoints — it restarts from the beginning. Worse, `GetFolderByServerRelativeUrl` does not surface pagination errors; it silently returns what it has.

**How to avoid:**
After every Files or Folders API response, inspect for `@odata.nextLink` in the response body. If present, follow it. Loop until `@odata.nextLink` is absent. Alternatively, use `GetItems` with a CAML query and `ListItemCollectionPosition` for controlled pagination. Never assume a single API response is complete.

```
while response.get('@odata.nextLink'):
    response = fetch(response['@odata.nextLink'])
    files.extend(response['value'])
```

**Warning signs:**
- Downloaded file count is suspiciously round (exactly 100, 200, etc.)
- Files from the beginning of the alphabetical list download but later ones are missing
- No errors in logs, but manifest shows fewer files than expected

**Phase to address:** Phase 1 (folder traversal / enumeration). Must be verified before any download logic is built on top of it.

---

### Pitfall 2: Guest Session Expiry Mid-Download Causes Silent 401/403 Without Retry

**What goes wrong:**
The Entra B2B guest session used to access a SharePoint shared link has a finite lifetime (access tokens typically expire in ~1 hour; conditional access policies on the host tenant may shorten this). When the session expires mid-run, subsequent HTTP requests return 401 or 403. If the download loop treats non-200 responses as a skip condition or catches the exception broadly and continues, every file after the expiry point is silently missed.

**Why it happens:**
The guest auth flow (email + OTP, now Entra B2B) produces browser-scoped session cookies (FedAuth, rtFa). These are not refresh-token-backed in the traditional sense when captured as cookies for automation. Once expired they cannot be silently renewed. Code that catches `requests.exceptions.RequestException` broadly and `continue`s will swallow auth failures identically to transient network errors.

**How to avoid:**
- Treat HTTP 401 and 403 as hard failures that halt the run and prompt re-authentication, not as retriable errors.
- Separately classify error categories: auth failure (401/403) = abort and re-auth; transient (429, 503, 5xx) = retry with backoff; permanent (404) = log as missing file; success (200, 206) = proceed.
- Before starting a large batch, validate the session with a lightweight probe request (e.g., fetch folder metadata) and fail fast if auth is stale.
- Log every non-200 response with its status code, URL, and timestamp. Never silently skip.

**Warning signs:**
- Downloads succeed for the first N minutes then stop appearing
- Log shows no errors but files after a certain timestamp are missing
- Session was established long before the run started (e.g., authenticated in the morning, ran in the afternoon)

**Phase to address:** Phase 1 (auth layer) and Phase 2 (download loop error handling).

---

### Pitfall 3: Large File Downloads (~2GB) Silently Corrupt or Truncate Without Streaming

**What goes wrong:**
SharePoint REST API `/$value` endpoint is documented to return file content directly, but confirmed GitHub issues show it returns incomplete content for large files. Even when content arrives intact, loading a 2GB file into memory via `response.content` or `response.read()` causes memory exhaustion or timeout on the read side, producing a truncated local file with no error raised by `requests`.

**Why it happens:**
- `requests.get(url).content` buffers the entire response in memory. At 2GB, Python processes may be killed by the OS or the socket times out before the buffer is full.
- The `requests` default timeout applies to the connection phase, not the total download duration. A 2GB file over a moderate connection may take 10+ minutes; the default response read has no timeout at all, leaving the connection open until the OS kills it.
- The `/$value` endpoint itself has a confirmed bug for large files (SharePoint/sp-dev-docs#5247).

**How to avoid:**
- Use `stream=True` on every file download request and write in chunks (e.g., 8MB chunks).
- Use the `download.aspx` URL (which supports byte-range requests) instead of `/$value` for file content.
- Set an explicit `timeout=(connect_timeout, read_timeout)` tuple in `requests.get`. For large files, `read_timeout` should be generous (e.g., 600s) but not `None`.
- After download, verify local file size against the `Content-Length` response header before computing the hash. Mismatch = corrupted download, retry.

**Warning signs:**
- Local file size is smaller than the size reported in the SharePoint manifest or file listing
- Python process memory usage spikes during downloads
- Downloads that work for small files fail silently for files > 500MB

**Phase to address:** Phase 2 (download engine). Chunk streaming must be the baseline, not an afterthought.

---

### Pitfall 4: SharePoint OTP Authentication Retired — Auth Model May Differ From Assumption

**What goes wrong:**
The project assumes email + one-time code (OTP) authentication. Microsoft retired SharePoint OTP authentication effective July 1, 2025 (SPO OTP). New sharing links now use Entra B2B guest accounts, not OTP codes. If the target SharePoint tenant has completed migration, the guest auth flow will be Entra B2B (which may involve MFA registration), not a simple email + 6-digit code. Code written for OTP flow will not work.

**Why it happens:**
The retirement rolled out between May and July 2025. Depending on when the specific sharing link was created and the host tenant's migration status, the link may use either OTP (legacy, still active until July 2026 for pre-migration links) or Entra B2B (current). As of March 2026, both modes may be in the wild simultaneously.

**How to avoid:**
- Before writing any auth automation, manually test the specific shared link to determine which flow it triggers: OTP code email, or Entra B2B guest invitation with MFA.
- Design the auth layer to be explicitly swappable — isolate auth from download logic behind a clean interface.
- Document which auth flow the specific target link uses and assert it at startup.
- If the link triggers Entra B2B with MFA, automated headless auth is harder; the design should fall back to "user manually authenticates in a browser, tool captures and uses the resulting session cookies."

**Warning signs:**
- Attempting OTP flow against a B2B-migrated link produces "Sorry, something went wrong. This organization has updated its guest access settings."
- The shared link URL structure differs from expected (B2B links have different URL formats)

**Phase to address:** Phase 1 (auth discovery and design). Validate actual auth flow on the specific target link before building anything.

---

### Pitfall 5: Exception Swallowing in Download Loops — The Silent Skip Pattern

**What goes wrong:**
This is almost certainly the direct cause of the previous Python script's silent file skips. A common pattern in download scripts:

```python
for file in files:
    try:
        download(file)
    except Exception:
        continue  # "handle" the error by skipping
```

Every error — auth failure, network timeout, API bug, wrong URL — causes the file to be silently skipped. The loop completes successfully. The manifest shows N files downloaded without indicating M were skipped.

**Why it happens:**
Developers write optimistic retry logic that degrades into "skip on any error." The `except Exception: continue` or `except Exception: pass` pattern is widely taught as "make it robust" but in a bulk download context it becomes a silent data loss vector.

**How to avoid:**
- Maintain an explicit `failed` list alongside the `downloaded` list. Every exception must be caught, logged with the full error, and appended to `failed`.
- At the end of a run, if `len(failed) > 0`, exit with a non-zero status code and print every failed file.
- The final manifest must include three categories: downloaded, failed (with reason), and not-attempted.
- Never use bare `except Exception: continue` in the download loop.

**Warning signs:**
- Script completes without errors but file count is less than expected
- Log file shows only success messages
- No "failed" or "error" section in the output

**Phase to address:** Phase 2 (download engine). Build the error-tracking scaffolding first, before any download logic.

---

### Pitfall 6: File Integrity Check Against Server-Side Hash Is Unreliable for Non-Binary Files

**What goes wrong:**
SharePoint is documented to modify certain uploaded files (primarily Office documents) server-side. Comparing a locally-computed hash against a hash fetched from the SharePoint API (e.g., `ListItem.File.ETag` or the `CheckSum` property) will fail for files SharePoint has modified, even if the local download is byte-for-byte what SharePoint now serves. This is a false positive corruption signal.

**Why it happens:**
SharePoint processes some file types (Word, Excel, PowerPoint) to add metadata or versioning markers. The stored file differs from the uploaded original.

**How to avoid:**
- For this project's file types (.E01, .L01 forensic evidence files), SharePoint modification is extremely unlikely — this only affects Office formats. Binary evidence files will not be altered.
- The correct integrity model is: hash the downloaded file after download, compare it against a hash computed from a reference set (if available) or record it in the manifest for the investigator to verify against the source custodian's known hashes.
- Do not rely on SharePoint's server-side hash values as ground truth for non-Microsoft file types. Compute hashes locally from the downloaded bytes.
- Use SHA-256 (not MD5) for the manifest, as forensic evidence collection may require cryptographically strong hashes.

**Warning signs:**
- Hash mismatch between server-reported and locally-computed hash for .docx files (expected)
- Hash mismatch for .E01 files (unexpected — investigate immediately)

**Phase to address:** Phase 3 (manifest and verification). Design the integrity model correctly from the start.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| `except Exception: continue` in download loop | Script doesn't crash on errors | Silent file skips — the exact bug being fixed | Never |
| Single-request file download (no streaming) | Simpler code | Memory exhaustion and timeouts on 2GB files | Never for this project |
| Hard-coded session cookies | Skip auth UI complexity | First run works, subsequent runs fail silently when cookies expire | Never — detect expiry explicitly |
| Skip manifest generation until "later" | Faster initial implementation | Forensic requirement not met; hard to add retroactively to running downloads | Never — manifest is the core value |
| Compute file count from folder listing without verifying pagination | Looks complete in tests | Under-counts files; validation passes against wrong baseline | Never |
| No retry on transient errors (429, 503) | Simpler loop | SharePoint throttling causes random missing files that look like success | Never for bulk operations |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| SharePoint REST `GetFolderByServerRelativeUrl` | Assuming one API call returns all files | Always follow `@odata.nextLink` until absent; validate total count against folder metadata |
| SharePoint `/$value` download endpoint | Using it for large files | Use `download.aspx` URL with byte-range support; stream with `requests(stream=True)` |
| Guest session cookies (FedAuth, rtFa) | Treating 401 as a retry-able error | 401/403 = auth expired, halt and re-auth; only retry 429/5xx |
| SharePoint throttling (429) | Ignoring `Retry-After` header or retrying immediately | Read and honor `Retry-After`; respect `RateLimit-*` headers; max 10 requests/second per user |
| Entra B2B vs OTP auth flow | Assuming OTP flow is still active | Probe the specific link's auth flow manually before coding; design auth layer as swappable |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Non-streamed 2GB download | OOM kill, incomplete local file, silent truncation | `stream=True`, 8MB chunk writes, explicit read timeout | Files > ~500MB |
| Sequential single-threaded downloads | Very slow for 100+ files | Parallel downloads with a bounded thread pool (e.g., 4 concurrent) | Acceptable for MVP; becomes painful at 50+ files |
| Re-listing folders on every retry | Redundant API calls, throttling risk | Cache the file listing; only re-fetch if enumeration itself fails | Any retry scenario |
| No progress tracking across runs | Full restart if interrupted mid-run | Persist a download state file; skip already-completed files on resume | Any run with 100+ large files |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Persisting session cookies to an unprotected file | Session hijack if file is readable by other processes | Store session state with `600` permissions; never commit to version control |
| Logging full URLs with auth tokens in query params | Token exposure in log files | Redact tokens from log output; log only file names and status codes |
| MD5 hashes in forensic manifest | MD5 is cryptographically broken; may not satisfy evidence chain-of-custody standards | Use SHA-256 minimum; SHA-512 if the investigation requires it |
| Trusting file size from API response as integrity proof | Truncated downloads pass size check if Content-Length is wrong | Verify both size AND hash; do not substitute one for the other |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No progress output during large downloads | User cannot tell if tool is running or hung | Print per-file progress with size and percentage; print overall progress (N of M files) |
| Only reporting success at the end | User learns of failures after hours of waiting | Report failures immediately as they occur; surface a running failure count |
| Ambiguous "done" message that doesn't state completeness | User doesn't know if all files were downloaded | End-of-run summary must state: X downloaded, Y failed, Z skipped — and exit non-zero if Y > 0 |
| Prompting for download destination after auth | Auth expires while user fumbles for path | Collect all inputs (destination path, URL) before initiating auth |

---

## "Looks Done But Isn't" Checklist

- [ ] **Pagination:** Verify total file count from the API against an independent source (SharePoint folder size shown in browser UI). A match confirms pagination is working. A lower count confirms truncation.
- [ ] **Large file integrity:** Test with a known file > 1GB. Compute SHA-256 before and after download. Any mismatch indicates streaming or endpoint issues.
- [ ] **Auth expiry simulation:** Start a download run, let the session expire (wait > 1 hour or clear cookies), observe whether the tool detects the expiry or silently continues with failures.
- [ ] **Partial download resume:** Kill the tool mid-run. Re-run. Verify already-downloaded files are not re-downloaded and failed files are retried.
- [ ] **Manifest completeness:** Compare manifest file count against SharePoint UI count. Manifest must include failed files, not only successes.
- [ ] **Non-zero exit on failures:** If any file fails to download, the tool must exit with a non-zero status code. Verify this.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Silent pagination truncation discovered after run | HIGH | Re-enumerate all folders with fixed pagination; compare against manifest; re-download missing files |
| Auth expired during run | LOW | Re-authenticate; use resume functionality to continue from last successful file |
| Corrupt/truncated large file | LOW | Tool should auto-detect via size mismatch; delete and re-download the specific file |
| OTP flow broken (Entra B2B migration) | MEDIUM | Manually authenticate in browser; export session cookies; update auth config; validate before re-running |
| Manifest missing (no manifest was generated) | HIGH | Cannot prove completeness retroactively; must re-download entire set with manifest generation enabled |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Pagination truncation (silent missing files) | Phase 1: Folder enumeration | Assert enumerated count matches SharePoint UI count before downloading |
| Auth expiry mid-run | Phase 1: Auth layer + Phase 2: Error handling | Simulate expiry during test; confirm tool halts with clear message |
| Large file corruption/truncation | Phase 2: Download engine | Hash verification test with a 1GB+ synthetic file |
| OTP vs Entra B2B auth flow mismatch | Phase 1: Auth discovery | Manually probe target link; document auth flow type in config |
| Exception swallowing / silent skip | Phase 2: Download loop | Intentionally inject a 403 mid-run; confirm it appears in failed list |
| Server-side hash unreliability | Phase 3: Manifest generation | Verify hashes are computed from local bytes, not server-provided values |

---

## Sources

- SharePoint sp-dev-docs Issue #5247 — Incomplete content on large file downloads via `/$value`: https://github.com/SharePoint/sp-dev-docs/issues/5247
- SharePoint sp-dev-docs Issue #1654 — `$skiptoken` pagination broken: https://github.com/SharePoint/sp-dev-docs/issues/1654
- Microsoft Q&A — Unable to retrieve files due to list view threshold: https://learn.microsoft.com/en-us/answers/questions/2149751/unable-to-retrieve-files-from-sharepoint-library-u
- PnPCore Issue #228 — TaskCanceled on 2GB+ file downloads: https://github.com/pnp/pnpcore/issues/228
- Office365-REST-Python-Client Issue #307 — Files not listed, pagination and URL handling bugs: https://github.com/vgrem/Office365-REST-Python-Client/issues/307
- rclone Issue #2599 — SharePoint modifies Office files, breaking integrity checks: https://github.com/rclone/rclone/issues/2599
- Microsoft Learn — Avoid throttling in SharePoint Online: https://learn.microsoft.com/en-us/sharepoint/dev/general-development/how-to-avoid-getting-throttled-or-blocked-in-sharepoint-online
- Steve Chen Blog — SharePoint OTP retirement July 2025: https://steve-chen.blog/2025/06/23/sharepoint-online-otp-authentication-gets-out-of-support-on-july-1st-2025/
- Office365 IT Pros — SPO OTP replaced by Entra B2B: https://office365itpros.com/2025/06/10/entra-id-b2b-collaboration-spo/
- Microsoft MC1243549 — Official retirement announcement: https://mc.merill.net/message/MC1243549
- Microsoft Learn — Configurable token lifetimes (Entra): https://learn.microsoft.com/en-us/entra/identity-platform/configurable-token-lifetimes
- RateLimit headers for proactive throttling management: https://devblogs.microsoft.com/microsoft365dev/prevent-throttling-in-your-application-by-using-ratelimit-headers-in-sharepoint-online/

---
*Pitfalls research for: SharePoint bulk downloader (guest/external auth, large files, forensic integrity)*
*Researched: 2026-03-27*
