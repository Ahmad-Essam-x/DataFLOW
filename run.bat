@echo off
setlocal enabledelayedexpansion
title Antigravity DataFlow - Local Visual ETL
cd /d "%~dp0"

echo ============================================================
echo   Starting Antigravity DataFlow (Visual ETL Engine)
echo ============================================================
echo.

set "PY_CMD="

:: 1. Check local virtual environment (.venv or venv)
if exist "%~dp0.venv312\Scripts\python.exe" (
    set "PY_CMD=%~dp0.venv312\Scripts\python.exe"
) else if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_CMD=%~dp0.venv\Scripts\python.exe"
) else if exist "%~dp0venv\Scripts\python.exe" (
    set "PY_CMD=%~dp0venv\Scripts\python.exe"
)

:: 2. Check Anaconda / Conda standard installations
if not defined PY_CMD (
    if exist "%USERPROFILE%\anaconda3\python.exe" (
        set "PY_CMD=%USERPROFILE%\anaconda3\python.exe"
    ) else if exist "%USERPROFILE%\miniconda3\python.exe" (
        set "PY_CMD=%USERPROFILE%\miniconda3\python.exe"
    ) else if exist "%LOCALAPPDATA%\anaconda3\python.exe" (
        set "PY_CMD=%LOCALAPPDATA%\anaconda3\python.exe"
    ) else if exist "C:\ProgramData\anaconda3\python.exe" (
        set "PY_CMD=C:\ProgramData\anaconda3\python.exe"
    )
)

:: 3. Check system 'python' on PATH
if not defined PY_CMD (
    where python >nul 2>nul
    if !errorlevel! equ 0 (
        set "PY_CMD=python"
    )
)

:: 4. Check Windows Python launcher 'py'
if not defined PY_CMD (
    where py >nul 2>nul
    if !errorlevel! equ 0 (
        set "PY_CMD=py"
    )
)

if not defined PY_CMD (
    echo [ERROR] No Python installation found on this system.
    echo Please install Python 3.10+ from https://www.python.org/
    echo and ensure "Add Python to PATH" is checked during installation.
    echo.
    pause
    exit /b 1
)

:: 5. Test if required packages are installed, auto-install if missing
"!PY_CMD!" -c "import flask, pandas, waitress" >nul 2>nul
if !errorlevel! neq 0 (
    echo [INFO] Detected missing dependencies. Installing requirements from requirements.txt...
    "!PY_CMD!" -m pip install -r "%~dp0requirements.txt"
    if !errorlevel! neq 0 (
        echo.
        echo [ERROR] Failed to install required packages.
        echo Please manually run: pip install -r requirements.txt
        pause
        exit /b 1
    )
)

:: 6. Launch Application (native desktop window; pass --browser to use the default browser instead)
echo [OK] Using Python environment: "!PY_CMD!"
echo [INFO] Starting Antigravity DataFlow desktop window...
echo.
"!PY_CMD!" desktop_app.py %*

if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Application exited with error code !errorlevel!.
    pause
)
