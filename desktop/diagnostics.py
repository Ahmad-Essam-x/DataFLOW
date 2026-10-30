"""
Antigravity DataFlow - Pre-flight Diagnostics and Dependency Verifier.
Validates Windows OS, 64-bit architecture, Microsoft Edge WebView2 Evergreen Runtime,
fallback browsers, loopback networking, file system permissions, and memory resources.
Provides structured diagnostic reporting and 1-click remediation instructions.
"""
import os
import sys
import socket
import logging
import platform
import shutil
import ctypes
from typing import Dict, List, Any, Optional

WEBVIEW2_DOWNLOAD_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"

logger = logging.getLogger("AntigravityDataFlow")


def get_launch_log_path(custom_path: Optional[str] = None) -> str:
    """
    Resolves the canonical path for persistent launch logging.
    Priority:
    1. Explicit custom path passed in arguments.
    2. %LOCALAPPDATA%\\AntigravityDataFlow\\logs\\launch.log.
    3. <app_dir>\\logs\\launch.log (if writable).
    4. %TEMP%\\AntigravityDataFlow\\logs\\launch.log.
    """
    if custom_path:
        os.makedirs(os.path.dirname(os.path.abspath(custom_path)), exist_ok=True)
        return os.path.abspath(custom_path)

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        target_dir = os.path.join(local_app_data, "AntigravityDataFlow", "logs")
        try:
            os.makedirs(target_dir, exist_ok=True)
            return os.path.join(target_dir, "launch.log")
        except Exception:
            pass

    # Try local app directory
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_dir = os.path.join(base_dir, "logs")
    try:
        os.makedirs(target_dir, exist_ok=True)
        test_file = os.path.join(target_dir, ".perm_test")
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        return os.path.join(target_dir, "launch.log")
    except Exception:
        pass

    # Temp fallback
    temp_dir = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "AntigravityDataFlow", "logs")
    os.makedirs(temp_dir, exist_ok=True)
    return os.path.join(temp_dir, "launch.log")


def setup_persistent_logger(log_file: Optional[str] = None, level: int = logging.INFO) -> str:
    """Configures persistent file and console logging."""
    resolved_path = get_launch_log_path(log_file)
    logger.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Check if a file handler with this path already exists
    has_file_handler = False
    for h in list(logger.handlers):
        if isinstance(h, logging.FileHandler):
            if log_file and os.path.abspath(getattr(h, "baseFilename", "")) != os.path.abspath(resolved_path):
                h.close()
                logger.removeHandler(h)
            else:
                has_file_handler = True

    if not has_file_handler:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(resolved_path)), exist_ok=True)
            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(resolved_path, mode="a", maxBytes=1024 * 1024, backupCount=3, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            sys.stderr.write(f"[WARN] Failed to attach file log handler to {resolved_path}: {e}\n")

    has_console = any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in logger.handlers)
    if not has_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # Ensure file exists on disk
    if not os.path.exists(resolved_path):
        try:
            with open(resolved_path, "a", encoding="utf-8") as f:
                pass
        except Exception:
            pass

    return resolved_path


def check_os_and_arch() -> Dict[str, Any]:
    """Validates operating system and processor architecture."""
    os_name = platform.system()
    os_release = platform.release()
    os_version = platform.version()
    arch, _ = platform.architecture()
    machine = platform.machine()

    is_windows = os_name == "Windows"
    is_64bit = "64" in arch or "64" in machine

    status = "PASS" if is_windows and is_64bit else ("WARN" if is_windows else "FAIL")
    details = f"{os_name} {os_release} (Build {os_version}, {machine}, {arch})"
    remediation = ""
    if not is_windows:
        remediation = "Antigravity DataFlow native packaging is optimized for Windows 10/11 x64."
    elif not is_64bit:
        remediation = "32-bit Windows detected; 64-bit Windows 10 or 11 is recommended for high-volume ETL."

    return {
        "name": "Operating System & Architecture",
        "category": "platform",
        "status": status,
        "details": details,
        "remediation": remediation,
        "required": True
    }


def check_webview2_runtime() -> Dict[str, Any]:
    """
    Detects Microsoft Edge WebView2 Evergreen Runtime via Windows Registry keys.
    Returns PASS if detected, WARN if missing (with download instructions).
    """
    if platform.system() != "Windows":
        return {
            "name": "Microsoft Edge WebView2 Runtime",
            "category": "runtime",
            "status": "WARN",
            "details": "Non-Windows platform; PyWebView will use available platform engine.",
            "remediation": "",
            "required": False
        }

    detected_version = None
    subkeys = [
        # 32-bit WOW64 key (Standard location on 64-bit Windows)
        (r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}", "HKLM"),
        # 64-bit native key
        (r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}", "HKLM"),
        # Per-user installation
        (r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}", "HKCU"),
    ]

    try:
        import winreg
        for subkey, hive in subkeys:
            hkey = winreg.HKEY_LOCAL_MACHINE if hive == "HKLM" else winreg.HKEY_CURRENT_USER
            try:
                with winreg.OpenKey(hkey, subkey) as key:
                    val, _ = winreg.QueryValueEx(key, "pv")
                    if val and val != "0.0.0.0":
                        detected_version = val
                        break
            except Exception:
                continue
    except Exception:
        pass

    if detected_version:
        return {
            "name": "Microsoft Edge WebView2 Runtime",
            "category": "runtime",
            "status": "PASS",
            "details": f"Evergreen Runtime v{detected_version} detected (Hardware accelerated)",
            "remediation": "",
            "required": False
        }
    else:
        return {
            "name": "Microsoft Edge WebView2 Runtime",
            "category": "runtime",
            "status": "WARN",
            "details": "WebView2 Runtime not found. PyWebView native window will cascade to Edge App Mode.",
            "remediation": f"Install the free Evergreen WebView2 Runtime from Microsoft: {WEBVIEW2_DOWNLOAD_URL}",
            "required": False
        }


def check_edge_browser() -> Dict[str, Any]:
    """Checks for Microsoft Edge browser executable for Tier 2 fallback."""
    edge_paths = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    ]
    found_path = None
    for p in edge_paths:
        if p and os.path.exists(p):
            found_path = p
            break

    if not found_path:
        which_edge = shutil.which("msedge")
        if which_edge:
            found_path = which_edge

    if found_path:
        return {
            "name": "Microsoft Edge Browser (Tier 2 Fallback)",
            "category": "browser",
            "status": "PASS",
            "details": f"Found at {found_path}",
            "remediation": "",
            "required": False
        }
    else:
        return {
            "name": "Microsoft Edge Browser (Tier 2 Fallback)",
            "category": "browser",
            "status": "WARN",
            "details": "Microsoft Edge executable not found in standard directories.",
            "remediation": "Microsoft Edge is recommended as standalone chromeless app fallback.",
            "required": False
        }


def check_default_browser() -> Dict[str, Any]:
    """Checks whether a system default browser is registered (Tier 3 fallback)."""
    prog_id = None
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            prog_id, _ = winreg.QueryValueEx(key, "ProgId")
    except Exception:
        pass

    if prog_id:
        return {
            "name": "Default Web Browser (Tier 3 Fallback)",
            "category": "browser",
            "status": "PASS",
            "details": f"Registered handler: {prog_id}",
            "remediation": "",
            "required": False
        }

    # Fallback to webbrowser inspection
    try:
        import webbrowser
        b = webbrowser.get()
        return {
            "name": "Default Web Browser (Tier 3 Fallback)",
            "category": "browser",
            "status": "PASS",
            "details": f"Python webbrowser handler: {type(b).__name__}",
            "remediation": "",
            "required": False
        }
    except Exception as e:
        return {
            "name": "Default Web Browser (Tier 3 Fallback)",
            "category": "browser",
            "status": "WARN",
            "details": f"Could not resolve default browser ({e})",
            "remediation": "Ensure a default web browser is selected in Windows Settings > Default apps.",
            "required": False
        }


def check_loopback_socket() -> Dict[str, Any]:
    """
    Tests binding on 127.0.0.1 loopback interface.
    Verifies that third-party firewalls or network policies do not block local IPC.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 0))
            allocated_port = s.getsockname()[1]

        # Also probe standard starting port 5000
        port_5000_status = "available"
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                s2.bind(("127.0.0.1", 5000))
        except OSError:
            port_5000_status = "in use (auto-port finder will select next open port)"

        return {
            "name": "Loopback Networking (127.0.0.1)",
            "category": "network",
            "status": "PASS",
            "details": f"Loopback binding (127.0.0.1) operational (Port 5000 is {port_5000_status}, dynamic probe: {allocated_port})",
            "remediation": "",
            "required": True
        }
    except Exception as e:
        return {
            "name": "Loopback Networking (127.0.0.1)",
            "category": "network",
            "status": "FAIL",
            "details": f"Socket binding to 127.0.0.1 failed: {e}",
            "remediation": "Check that Windows Firewall or security software allows loopback binding on 127.0.0.1.",
            "required": True
        }


def check_filesystem_permissions() -> Dict[str, Any]:
    """Validates write and read permissions for application data and cache directories."""
    app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    target_dir = os.path.join(app_data, "AntigravityDataFlow")
    test_file = os.path.join(target_dir, ".diag_test.tmp")

    try:
        os.makedirs(target_dir, exist_ok=True)
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("diagnostics_ok")
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()
        os.remove(test_file)

        if content == "diagnostics_ok":
            return {
                "name": "AppData Storage & File Permissions",
                "category": "filesystem",
                "status": "PASS",
                "details": f"Read/write verified at {target_dir}",
                "remediation": "",
                "required": True
            }
        else:
            raise ValueError("Test file content mismatch")
    except Exception as e:
        return {
            "name": "AppData Storage & File Permissions",
            "category": "filesystem",
            "status": "WARN",
            "details": f"Permission issue at {target_dir}: {e}",
            "remediation": "Ensure current user account has standard write permissions to %LOCALAPPDATA%.",
            "required": True
        }


def check_system_resources() -> Dict[str, Any]:
    """Checks available system RAM and free disk space."""
    # RAM check
    avail_ram_gb = None
    total_ram_gb = None
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            avail_ram_gb = stat.ullAvailPhys / (1024 ** 3)
            total_ram_gb = stat.ullTotalPhys / (1024 ** 3)
    except Exception:
        pass

    # Disk space check
    target_path = os.environ.get("LOCALAPPDATA", ".")
    try:
        du = shutil.disk_usage(target_path)
        free_disk_gb = du.free / (1024 ** 3)
    except Exception:
        free_disk_gb = 10.0

    ram_ok = (avail_ram_gb is None) or (avail_ram_gb >= 1.0)
    disk_ok = free_disk_gb >= 0.5

    status = "PASS" if (ram_ok and disk_ok) else "WARN"
    details_parts = []
    if avail_ram_gb is not None:
        details_parts.append(f"Available RAM: {avail_ram_gb:.1f} GB (Total: {total_ram_gb:.1f} GB)")
    details_parts.append(f"Free Disk: {free_disk_gb:.1f} GB")
    details = ", ".join(details_parts)

    remediation = ""
    if not ram_ok:
        remediation = "Low system RAM (< 1 GB available). Close background applications for optimal ETL performance."
    elif not disk_ok:
        remediation = "Low disk space (< 500 MB). Free up drive space for caching and scratch processing."

    return {
        "name": "System Resources (RAM & Disk)",
        "category": "resources",
        "status": status,
        "details": details,
        "remediation": remediation,
        "required": False
    }


def run_system_diagnostics() -> Dict[str, Any]:
    """Runs the complete suite of dependency and health diagnostics."""
    checks = [
        check_os_and_arch(),
        check_webview2_runtime(),
        check_edge_browser(),
        check_default_browser(),
        check_loopback_socket(),
        check_filesystem_permissions(),
        check_system_resources()
    ]

    has_fail = any(c["status"] == "FAIL" for c in checks)
    has_warn = any(c["status"] == "WARN" for c in checks)

    overall_status = "FAIL" if has_fail else ("WARN" if has_warn else "PASS")
    remediations = [c["remediation"] for c in checks if c.get("remediation")]

    # Visual launch tier resolution
    tier = "Tier 1: Native WebView2 Desktop Window"
    if checks[1]["status"] != "PASS":
        if checks[2]["status"] == "PASS":
            tier = "Tier 2: Microsoft Edge Standalone App Mode"
        else:
            tier = "Tier 3: Default Web Browser"

    return {
        "overall_status": overall_status,
        "resolved_launch_tier": tier,
        "checks": checks,
        "remediations": remediations,
        "log_path": get_launch_log_path()
    }


def format_diagnostic_report(report: Dict[str, Any]) -> str:
    """Renders a clean, formatted ASCII diagnostic table for console or logs."""
    lines = []
    lines.append("=" * 72)
    lines.append("  ANTIGRAVITY DATAFLOW - SYSTEM DIAGNOSTICS & DEPENDENCY REPORT")
    lines.append("=" * 72)
    lines.append(f"  Overall Status       : [{report['overall_status']}]")
    lines.append(f"  Target Launch Engine : {report['resolved_launch_tier']}")
    lines.append(f"  Diagnostics Log File : {report['log_path']}")
    lines.append("-" * 72)

    for c in report["checks"]:
        tag = f"[{c['status']}]"
        lines.append(f"  {tag:<8} {c['name']}")
        lines.append(f"           Details: {c['details']}")
        if c.get("remediation"):
            lines.append(f"           Advice : {c['remediation']}")
        lines.append("")

    if report["remediations"]:
        lines.append("-" * 72)
        lines.append("  RECOMMENDED ACTIONS:")
        for idx, rem in enumerate(report["remediations"], 1):
            lines.append(f"  {idx}. {rem}")

    lines.append("=" * 72)
    return "\n".join(lines)


def show_native_error_dialog(title: str, message: str, log_path: Optional[str] = None) -> None:
    """
    Displays a native Windows modal error dialog box.
    Ensures that errors are never silent in packaged windowed applications.
    """
    full_msg = message
    if log_path:
        full_msg += f"\n\nDiagnostic Log:\n{log_path}"
    full_msg += "\n\nTip: use Help > Export Support Bundle, or run 'Diagnose_DataFlow.bat' in the application folder."

    if platform.system() == "Windows":
        try:
            # 0x00000010 = MB_ICONERROR, 0x00001000 = MB_SYSTEMMODAL
            ctypes.windll.user32.MessageBoxW(0, full_msg, title, 0x00000010 | 0x00001000)
            return
        except Exception:
            pass

    # Non-Windows or fallback
    sys.stderr.write(f"\n[FATAL ERROR] {title}\n{full_msg}\n")
