# Antigravity DataFlow - Distribution, Installation & Diagnostic Guide

This guide explains how to package, install, run, and diagnose **Antigravity DataFlow** on any Windows machine.

---

## 1. Quick Start Installation

**Distribution Bundle**: `dist/AntigravityDataFlow_Windows_x64.zip`  
**Prerequisites**: Windows 10 or 11 (64-bit). Python is **not required**.

### Step-by-Step Installation:
1. Transfer `AntigravityDataFlow_Windows_x64.zip` to the target computer.
2. Right-click and choose **Extract All...** to an uncompressed folder (e.g. `C:\Users\%USERNAME%\AppData\Local\Programs\AntigravityDataFlow` or `C:\AntigravityDataFlow`).
3. Inside the extracted folder, double-click:
   - **`Install_DataFlow.bat`**
4. What the installer does automatically:
   - **Pre-flight Checks**: Validates Windows OS version, 64-bit architecture, loopback networking on `127.0.0.1`, and file write permissions.
   - **Shortcuts**: Creates **Desktop** and **Start Menu** shortcuts with high-resolution app icons.
   - **Dependency Verification**: Confirms Microsoft Edge WebView2 runtime availability.
   - **Launch Option**: Offers to launch the app immediately.

---

## 2. Multi-Tier Visual Fallback Architecture

To ensure the application **never fails silently** and works across diverse enterprise environments, Antigravity DataFlow uses an intelligent 3-tier visual fallback hierarchy:

| Tier | Engine | Description |
|---|---|---|
| **Tier 1 (Preferred)** | **Microsoft Edge WebView2 (PyWebView)** | Chromeless native desktop application window with full hardware acceleration and system integration. |
| **Tier 2 (Fallback 1)** | **Microsoft Edge App Mode** | If WebView2 runtime is missing or blocked, automatically launches standalone chromeless Edge (`msedge.exe --app=http://127.0.0.1:<port>`). |
| **Tier 3 (Fallback 2)** | **Default Web Browser** | If Microsoft Edge is unavailable, automatically routes to the user's default browser (Google Chrome, Firefox, Brave, etc.). |
| **Fatal Handler** | **Native Windows Dialog (`MessageBoxW`)** | If local socket binding fails or a catastrophic error occurs, a native Windows modal error dialog appears with the exact cause, directing the user to the log and diagnostic tool. |

---

## 3. Troubleshooting & 1-Click Diagnostics

If the application does not launch or you encounter environment issues:

### 1-Click Diagnostic Tool:
Double-click **`Diagnose_DataFlow.bat`** in the application folder, or run:
```cmd
AntigravityDataFlow.exe --diagnose
```
This prints an instant system report evaluating:
- `[PASS / FAIL]` Operating System & Architecture
- `[PASS / WARN]` Microsoft Edge WebView2 Evergreen Runtime
- `[PASS / WARN]` Microsoft Edge Executable Path
- `[PASS / WARN]` Default Web Browser Registration
- `[PASS / FAIL]` Loopback Socket Binding on `127.0.0.1`
- `[PASS / FAIL]` File Storage & Write Permissions (`%LOCALAPPDATA%\AntigravityDataFlow`)
- `[PASS / WARN]` System Resources (RAM and Disk Space)

### Persistent Launch Logs:
All launch events, port assignments, and errors are continuously logged to:
```
%LOCALAPPDATA%\AntigravityDataFlow\logs\launch.log
```
Pressing `1` inside `Diagnose_DataFlow.bat` immediately opens this log file in Notepad.

### Common Solutions:
1. **WebView2 Runtime Missing**:
   - Run `Diagnose_DataFlow.bat` and press `2` to open Microsoft's official download page, or download directly from:  
     `https://go.microsoft.com/fwlink/p/?LinkId=2124703`
2. **Loopback Blocked by Antivirus / Firewall**:
   - Ensure your firewall allows local loopback TCP traffic between processes on `127.0.0.1`.
3. **Port Conflict**:
   - The application automatically scans and binds to the first open port starting at `5000`. You can also specify a custom port:
     ```cmd
     AntigravityDataFlow.exe --port 5050
     ```

---

## 4. Building the Standalone Package

To rebuild the standalone Windows distribution from source:
```powershell
python build_desktop.py
```
This builds `AntigravityDataFlow.exe`, includes all helper batch scripts, bundles assets/workflows/data, and outputs `dist/AntigravityDataFlow_Windows_x64.zip`.
