@echo off
rem Antigravity DataFlow - run the built-in diagnostics and show where the logs are.
rem Works for the installed app (next to AntigravityDataFlow.exe) and from a source checkout (py desktop_app.py).
setlocal
title Antigravity DataFlow - Diagnostics
cd /d "%~dp0"

if exist "%~dp0AntigravityDataFlow.exe" (
    "%~dp0AntigravityDataFlow.exe" --diagnose
) else if exist "%~dp0.venv312\Scripts\python.exe" (
    "%~dp0.venv312\Scripts\python.exe" desktop_app.py --diagnose
) else (
    py desktop_app.py --diagnose
)

echo.
echo Logs are in: %LOCALAPPDATA%\AntigravityDataFlow\logs
echo   app.log     - application log (errors include a reference id)
echo   launch.log  - startup log
echo In the app you can also use Help ^> Export Support Bundle to create a zip to send to support.
echo.
set /p OPENLOG="Open the logs folder now? (y/N) "
if /i "%OPENLOG%"=="y" start "" explorer "%LOCALAPPDATA%\AntigravityDataFlow\logs"
endlocal
