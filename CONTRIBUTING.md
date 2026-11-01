# Contributing

## Set up

Python 3.12 on Windows.

```powershell
py -3.12 -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv312\Scripts\python.exe -m playwright install chromium   # for the browser tests
```

`requirements.txt` holds the exact versions the test suite passes on. Database connectors (Snowflake, PostgreSQL, SQLAlchemy) are optional and live in `requirements-optional.txt`.

## Run

```powershell
.\run.bat                              # desktop window (PyWebView + WebView2)
.\.venv312\Scripts\python.exe desktop_app.py --browser   # same app in your browser
.\.venv312\Scripts\python.exe run.py   # plain web server
```

## Test

```powershell
.\.venv312\Scripts\python.exe -m pytest tests
```

- Tests run against a throwaway data folder (`DATAFLOW_HOME`, see `tests/conftest.py`). A test run must not change any tracked file; CI checks this.
- `tests/golden/` holds expected-output cases per tool (`build_cases.py` writes them). Mark a case `verified` only after comparing it with a real Alteryx run, and say where the output came from.
- `tests/test_exe_smoke.py` runs the built EXE; it is skipped until you have run `build_desktop.py`.

## Generated documentation

`docs/TOOL_REFERENCE.md` and `docs/ALTERYX_COMPATIBILITY.md` are generated; do not edit them by hand.

```powershell
.\.venv312\Scripts\python.exe scripts\generate_tool_reference.py
.\.venv312\Scripts\python.exe scripts\generate_compatibility.py
```

When you add a tool: write the node (`backend/engine/nodes/`), add it to `NODE_MODULES` and `TOOL_METADATA` in `registry.py`, add a config panel in `static/js/config_panel.js`, add notes to `scripts/generate_tool_reference.py`, add golden cases, then regenerate the docs. Tests fail until each step is done.

## Security rules for changes

- Generated or user code runs only through `backend/engine/sandbox.py`.
- Anything that sends data to an LLM goes through `get_provider()` (host approval, endpoint validation, key lookup).
- Never write an API key to a file; use `backend/engine/ai/secrets.py`.
- New API routes live under `/api/` so the local-API guard applies.

## Shipping a fix to teammates

1. Make the change, run the tests, commit.
2. Raise the number in `backend/_version.py` (for example `2.1.0` to `2.1.1`) and rename the `Unreleased` section in `CHANGELOG.md` to `2.1.1` with a one-line summary. Commit and push the branch.
3. Check everything without publishing: `py scripts/publish_release.py`. It refuses if there are uncommitted changes, the tag exists, the changelog has no section for this version, commits are unpushed, or tests fail.
4. Publish: `py scripts/publish_release.py --push`. This tags `v2.1.1` and pushes the tag.
5. GitHub Actions builds the app and installer (about 15 minutes) and attaches them to a Release. Watch the **Actions** tab.
6. Tell teammates. They open **Help > Check for Updates**, which opens the Releases page, and install the newest version.

The build ships only files tracked by git under `static`, `templates`, `data`, `workflows` and `assets`, so `git add` any new file in those folders first.

See "Building a release" in [DISTRIBUTION_GUIDE.md](DISTRIBUTION_GUIDE.md) for building locally without CI. Teammates need read access to this private repository to download releases.
