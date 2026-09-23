@echo off
set "APP_DIR=%~dp0"
set "APP_EXE=%APP_DIR%AntigravityDataFlow.exe"

if exist "%APP_EXE%" (
    start "" "%APP_EXE%" %*
    exit /b 0
)

:: 1. Read saved Python interpreter if available
set "PYTHON_EXE="
if exist "%APP_DIR%.python_env.bat" (
    call "%APP_DIR%.python_env.bat"
)

:: 2. Check if 'python' is on PATH
if not defined PYTHON_EXE (
    where python >nul 2>&1 && set "PYTHON_EXE=python"
)

:: 3. Check Python launcher
if not defined PYTHON_EXE (
    where py >nul 2>&1 && set "PYTHON_EXE=py -3"
)

:: 4. Check standard AppData Python installations
if not defined PYTHON_EXE (
    for %%V in (313 312 311 310 39) do (
        if not defined PYTHON_EXE (
            if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
                set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
            )
        )
    )
)

:: 5. Check Program Files and Conda
if not defined PYTHON_EXE (
    for %%V in (313 312 311 310 39) do (
        if not defined PYTHON_EXE (
            if exist "%ProgramFiles%\Python%%V\python.exe" (
                set "PYTHON_EXE=%ProgramFiles%\Python%%V\python.exe"
            )
        )
    )
)
if not defined PYTHON_EXE (
    if exist "%USERPROFILE%\anaconda3\python.exe" set "PYTHON_EXE=%USERPROFILE%\anaconda3\python.exe"
    if exist "%USERPROFILE%\miniconda3\python.exe" set "PYTHON_EXE=%USERPROFILE%\miniconda3\python.exe"
)

if not defined PYTHON_EXE (
    echo.
    echo ========================================================================
    echo  [ERROR] Python was not found on this machine!
    echo  Please run Install_DataFlow.bat first to set up your environment.
    echo ========================================================================
    echo.
    pause
    exit /b 1
)

start "" %PYTHON_EXE% "%APP_DIR%desktop_app.py" %*
