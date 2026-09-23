@echo off
setlocal EnableDelayedExpansion
title Antigravity DataFlow - System Diagnostics

echo ========================================================================
echo   ANTIGRAVITY DATAFLOW - SYSTEM AND DEPENDENCY DIAGNOSTICS
echo ========================================================================
echo.
echo Running diagnostic suite to verify operating system, WebView2 runtime,
echo fallback browsers, loopback networking, and permissions...
echo.

set "APP_DIR=%~dp0"
set "APP_EXE=%APP_DIR%AntigravityDataFlow.exe"

if exist "%APP_EXE%" (
    "%APP_EXE%" --diagnose
    goto POST_DIAG
)

:: Read saved Python interpreter if available
set "PYTHON_EXE="
if exist "%APP_DIR%.python_env.bat" (
    call "%APP_DIR%.python_env.bat"
)
if not defined PYTHON_EXE where python >nul 2>&1 && set "PYTHON_EXE=python"
if not defined PYTHON_EXE where py >nul 2>&1 && set "PYTHON_EXE=py -3"
if not defined PYTHON_EXE (
    for %%V in (313 312 311 310 39) do (
        if not defined PYTHON_EXE (
            if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
                set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
            )
        )
    )
)
if not defined PYTHON_EXE (
    if exist "%USERPROFILE%\anaconda3\python.exe" set "PYTHON_EXE=%USERPROFILE%\anaconda3\python.exe"
)

if not defined PYTHON_EXE (
    echo [ERROR] Python not found on system. Run Install_DataFlow.bat to install or locate Python.
    pause
    exit /b 1
)

echo [INFO] Running in development mode using Python interpreter: !PYTHON_EXE!
!PYTHON_EXE! "%APP_DIR%desktop_app.py" --diagnose

:POST_DIAG
echo.
set "LOG_PATH=%LOCALAPPDATA%\AntigravityDataFlow\logs\launch.log"
if exist "%LOG_PATH%" (
    echo Detailed launch log available at:
    echo %LOG_PATH%
    echo.
)

:MENU
echo ------------------------------------------------------------------------
echo [1] Open Launch Log in Notepad
echo [2] Download Microsoft Edge WebView2 Evergreen Runtime
echo [3] Exit Diagnostics
echo ------------------------------------------------------------------------
set /p CHOICE="Select an option (1-3) [default: 3]: "

if "%CHOICE%"=="1" (
    if exist "%LOG_PATH%" (
        start notepad.exe "%LOG_PATH%"
    ) else (
        echo [WARN] Launch log file has not been created yet. Launch the app once to generate it.
    )
    goto MENU
)

if "%CHOICE%"=="2" (
    echo Opening Microsoft WebView2 Evergreen Runtime download page...
    start https://go.microsoft.com/fwlink/p/?LinkId=2124703
    goto MENU
)

echo Exiting diagnostics.
exit /b 0
