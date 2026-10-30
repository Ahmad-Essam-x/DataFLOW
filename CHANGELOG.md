# Changelog

## Unreleased
### Security
- Schema Fit generated code runs in an isolated process with an allowlist check, scrubbed environment, time limit and memory cap (the previous in-process check could be bypassed).
- The local server rejects requests with an unexpected Host or Origin and requires a per-launch session cookie, so web pages in your browser cannot call it.
- LLM API keys are kept in Windows Credential Manager and never written to workflow, autosave, backup, template or package files; keys already saved in older files are moved on first start.
- LLM tools ask once before sending data to a non-local host (including LAN servers); endpoint URLs are validated and redirects are never followed.
- Gemini keys are sent in a header instead of the URL; API errors no longer expose internal paths.

### Added
- Running Total and Dynamic Rename are now available in the tool palette with configuration panels.
- Help > Export Support Bundle (logs, version, redacted settings; never workflows, data or keys). About shows the real version.
- Installer (per-user, no administrator rights), build script with version stamp, EXE smoke test, CI build and release jobs.
- Documentation: Tool Reference and Alteryx Compatibility (generated), install and support guide, golden-result tests per tool.
- Importing an Alteryx workflow now lists every unsupported tool that was replaced by a pass-through placeholder.
- Single source of truth for the version (`backend/_version.py`).
- Single-instance guard for the desktop window; uncaught exceptions are logged.

### Fixed
- Alteryx Filter conditions are imported as case-sensitive text comparisons, as in Alteryx.
- Sort puts nulls first when ascending and last when descending, and keeps equal keys in input order.
- The built app could not run any workflow because tools were discovered by scanning files; discovery no longer depends on the file system.
- Locked (frozen) node results are reused only when the node's settings are unchanged; edited nodes or other workflows reusing a node id no longer load stale data.
- Spill-cache writes on a full disk keep data in memory instead of failing.
- Freezing/locking a node was ignored on workflows that ran on the DuckDB fast path.
- The DuckDB fast path ignored Select renames and drops for Select tools built in the UI (wrong columns, no error).
- `requirements.txt` was missing `requests`, `pydantic`, `psutil`, `pillow` (clean installs crashed at startup).
- Removed the old Install/Launch batch scripts and the machine-specific build spec.


### Changed
- Frozen builds keep all user data in `%LOCALAPPDATA%\AntigravityDataFlow` (one-time migration from the old locations). Nothing is written into the install folder.
- Settings, connections and workflow saves are written atomically (no half-written files after a crash).
- Unexpected API errors return a reference id; details go to `%LOCALAPPDATA%\AntigravityDataFlow\logs\app.log` (rotating, with stack traces).
- `run.bat` now opens the standalone desktop window; use `--browser` for the browser.
