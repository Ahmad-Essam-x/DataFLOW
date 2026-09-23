@echo off
set "APP_DIR=%~dp0"
set "APP_EXE=%APP_DIR%AntigravityDataFlow.exe"

if exist "%APP_EXE%" (
    start "" "%APP_EXE%" %*
) else (
    start "" python "%APP_DIR%desktop_app.py" %*
)
