@echo off
setlocal EnableDelayedExpansion
title Antigravity DataFlow - Desktop Setup and Installation

echo ========================================================================
echo   ANTIGRAVITY DATAFLOW - DESKTOP SETUP AND INSTALLATION
echo ========================================================================
echo.
echo Installing Antigravity DataFlow for current user: %USERNAME%
echo Application directory: %~dp0
echo.

set "APP_DIR=%~dp0"
set "APP_EXE=%APP_DIR%AntigravityDataFlow.exe"

:: Detect Python if running in development mode
set "PYTHON_EXE=python"
if exist "%USERPROFILE%\anaconda3\python.exe" (
    set "PYTHON_EXE=%USERPROFILE%\anaconda3\python.exe"
)

:: 1. Pre-flight dependency check
echo [STEP 1/3] Checking system environment and runtime dependencies...
if exist "%APP_EXE%" (
    "%APP_EXE%" --check-deps
) else (
    "%PYTHON_EXE%" "%APP_DIR%desktop_app.py" --check-deps
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [WARNING] Some dependencies or configuration settings require attention.
    echo Running full diagnostics...
    if exist "%APP_EXE%" (
        "%APP_EXE%" --diagnose
    ) else (
        "%PYTHON_EXE%" "%APP_DIR%desktop_app.py" --diagnose
    )
    echo.
) else (
    echo [PASS] Core system and networking requirements verified.
)

:: 2. Create Windows Desktop and Start Menu shortcuts
echo.
echo [STEP 2/3] Installing Windows Desktop and Start Menu shortcuts...
if exist "%APP_EXE%" (
    "%APP_EXE%" --create-shortcut
) else (
    "%PYTHON_EXE%" "%APP_DIR%desktop_app.py" --create-shortcut
)

:: 3. Launch prompt
echo.
echo [STEP 3/3] Installation completed successfully!
echo.
echo ========================================================================
echo  Antigravity DataFlow is ready to use!
echo  - Desktop shortcut created: %USERPROFILE%\Desktop\Antigravity DataFlow.lnk
echo  - Start Menu shortcut created in Programs
echo ========================================================================
echo.

set /p LAUNCH="Would you like to launch Antigravity DataFlow now? (Y/N) [Y]: "
if /i "%LAUNCH%"=="N" goto END

echo Starting Antigravity DataFlow...
if exist "%APP_EXE%" (
    start "" "%APP_EXE%"
) else (
    start "" "%PYTHON_EXE%" "%APP_DIR%desktop_app.py"
)

:END
echo Done. You may close this window.
timeout /t 3 >nul 2>&1 || ping 127.0.0.1 -n 4 >nul
exit /b 0
