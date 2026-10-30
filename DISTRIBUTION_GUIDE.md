# Antigravity DataFlow - Install, Support and Release Guide

For people who install and support DataFlow on Windows, and for whoever builds a release.

---

## 1. Install (end users)

**Requirements:** Windows 10 or 11, 64-bit. Python is **not** needed. No administrator rights are needed.

1. Get `AntigravityDataFlow_Setup_<version>.exe` and its `.sha256` file from the team's release location.
2. Check the file is intact (optional but recommended). In PowerShell:
   ```powershell
   (Get-FileHash .\AntigravityDataFlow_Setup_<version>.exe -Algorithm SHA256).Hash
   ```
   The result must match the value in the `.sha256` file.
3. Double-click the installer and follow the steps. It installs for your user only, to `%LOCALAPPDATA%\Programs\AntigravityDataFlow`, and adds a Start Menu entry (desktop shortcut is optional).
4. **Windows SmartScreen:** until the installer is code-signed, Windows may show *"Windows protected your PC"*. Choose **More info**, then **Run anyway**. This warning goes away once a signing certificate is in place.
5. Start **Antigravity DataFlow** from the Start Menu.

**Upgrade:** run the newer installer. It replaces the program files and keeps your workflows and settings.
**Uninstall:** Settings > Apps > Antigravity DataFlow > Uninstall. You are asked whether to also delete your data; the default is to keep it.

### Where things are stored
| What | Where |
|---|---|
| Program | `%LOCALAPPDATA%\Programs\AntigravityDataFlow` |
| Your workflows, settings, saved connections, outputs | `%LOCALAPPDATA%\AntigravityDataFlow` |
| Logs | `%LOCALAPPDATA%\AntigravityDataFlow\logs` |

To back up your work, copy the `workflows` folder under `%LOCALAPPDATA%\AntigravityDataFlow`.

### Privacy and AI features
- DataFlow runs on your computer. Workflows and data stay on it.
- **LLM Process** and **Schema Fit** send cell values to the AI endpoint you configure. A local endpoint (Ollama or LM Studio on this PC) sends nothing off the machine. For any other host - including company servers on your network - DataFlow asks you to approve the host once before it sends data.
- API keys are kept in the Windows Credential Manager, never in workflow files.

---

## 2. Troubleshooting and support

If the app does not open or misbehaves:

1. In the app: **Help > Export Support Bundle**. It creates a zip with logs, version and system information. It does **not** contain workflows, data or keys, but logs can mention file names and folder paths, so check it before sending outside your organization.
2. If the app will not open, run `Diagnose_DataFlow.bat` from the program folder (or `AntigravityDataFlow.exe --diagnose`). It checks Windows version, WebView2, networking on `127.0.0.1`, folder permissions and memory/disk.
3. Logs: `%LOCALAPPDATA%\AntigravityDataFlow\logs\app.log` (errors show a reference id also shown in the app) and `launch.log`.

Common causes:
- **WebView2 runtime missing:** install it from <https://go.microsoft.com/fwlink/p/?LinkId=2124703>. Without it DataFlow falls back to an Edge window or your default browser.
- **"DataFlow is already running":** only one window per Windows user is allowed; switch to the existing window.
- **Security software blocks the app:** allow `AntigravityDataFlow.exe` and loopback (`127.0.0.1`) traffic.

---

## 3. Building a release (maintainers)

One-time setup (Python 3.12):
```powershell
py -3.12 -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Test, build, package:
```powershell
.\.venv312\Scripts\python.exe -m pytest tests
.\.venv312\Scripts\python.exe build_desktop.py                 # dist\AntigravityDataFlow\ and a portable zip
ISCC.exe /DAppVersion=<version> installer\DataFlow.iss          # dist\installer\AntigravityDataFlow_Setup_<version>.exe
```
- The version comes from `backend/_version.py`. Update it and `CHANGELOG.md` first.
- The build ships only git-tracked files and only the curated workflows (see `RELEASE_WORKFLOWS` in `build_desktop.py`). `tests/test_release_payload.py` fails if a personal path, customer file or API key would be included.
- Publish a SHA-256 next to the installer: `(Get-FileHash <installer> -Algorithm SHA256).Hash`.
- **Code signing:** request a code-signing certificate from IT, then enable `SignTool` in `installer/DataFlow.iss` and sign `AntigravityDataFlow.exe` and the installer.

### Release checklist
1. Version and changelog updated; all tests pass.
2. Build and installer succeed; SHA-256 recorded.
3. On a clean Windows machine, as a standard user: install, open a sample workflow and run it, **Help > Export Support Bundle**, upgrade over the previous version, uninstall (data kept).
4. Tag the release in git and publish installer and checksum.
