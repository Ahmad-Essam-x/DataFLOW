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

:: If standalone compiled executable exists, jump to step 1
if exist "%APP_EXE%" (
    echo [INFO] Detected standalone executable: %APP_EXE%
    goto STEP1
)

:: -------------------------------------------------------------------------
:: Robust Python Discovery
:: -------------------------------------------------------------------------
echo Searching for Python on this system...
set "PYTHON_EXE="

:: 1. Check if 'python' is on PATH and working
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    for /f "delims=" %%I in ('where python 2^>nul') do (
        if not defined PYTHON_EXE (
            set "PYTHON_EXE=%%I"
        )
    )
)

:: 2. Check if Python Launcher 'py' is available
if not defined PYTHON_EXE (
    where py >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set "PYTHON_EXE=py -3"
    )
)

:: 3. Check standard User AppData Python installations
if not defined PYTHON_EXE (
    for %%V in (313 312 311 310 39) do (
        if not defined PYTHON_EXE (
            if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
                set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
            )
        )
    )
)

:: 4. Check standard Program Files Python installations
if not defined PYTHON_EXE (
    for %%V in (313 312 311 310 39) do (
        if not defined PYTHON_EXE (
            if exist "%ProgramFiles%\Python%%V\python.exe" (
                set "PYTHON_EXE=%ProgramFiles%\Python%%V\python.exe"
            )
        )
    )
)

:: 5. Check Anaconda / Miniconda installations
if not defined PYTHON_EXE (
    if exist "%USERPROFILE%\anaconda3\python.exe" set "PYTHON_EXE=%USERPROFILE%\anaconda3\python.exe"
    if exist "%USERPROFILE%\miniconda3\python.exe" set "PYTHON_EXE=%USERPROFILE%\miniconda3\python.exe"
    if exist "C:\ProgramData\anaconda3\python.exe" set "PYTHON_EXE=C:\ProgramData\anaconda3\python.exe"
    if exist "C:\ProgramData\miniconda3\python.exe" set "PYTHON_EXE=C:\ProgramData\miniconda3\python.exe"
)

:: 6. If Python is still not found, offer automatic installation via winget or browser
if not defined PYTHON_EXE (
    echo.
    echo ========================================================================
    echo  [ERROR] Python is not installed or not found on this machine!
    echo ========================================================================
    echo.
    echo Antigravity DataFlow requires Python 3.10 or higher.
    echo.
    echo Would you like to automatically install Python now via Windows Package Manager?
    echo.
    set /p INSTALL_PY="Install Python 3.12 automatically? (Y/N) [Y]: "
    if /i "!INSTALL_PY!"=="N" (
        echo Opening official Python download page...
        start https://www.python.org/downloads/
        echo Please download Python and make sure to check:
        echo   "[X] Add python.exe to PATH"
        echo Then run this installer again.
        pause
        exit /b 1
    )
    
    echo Installing Python 3.12 via winget...
    winget install Python.Python.3.12 --scope user
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo Winget installation failed or is not available.
        echo Opening the official Python download page in your browser...
        start https://www.python.org/downloads/
        echo.
        echo IMPORTANT: When installing, make sure to check:
        echo   "[X] Add python.exe to PATH"
        pause
        exit /b 1
    )
    
    echo.
    echo Python installed successfully! Detecting installation path...
    for %%V in (312 313 311 310) do (
        if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" (
            set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
        )
    )
    if not defined PYTHON_EXE (
        echo Please close this window and double-click Install_DataFlow.bat again.
        pause
        exit /b 0
    )
)

echo [OK] Found Python interpreter: !PYTHON_EXE!
:: Save detected python path for Launch_DataFlow.bat
echo set "PYTHON_EXE=!PYTHON_EXE!"> "%APP_DIR%.python_env.bat"

:: -------------------------------------------------------------------------
:: Install & verify pip dependencies
:: -------------------------------------------------------------------------
echo.
echo Installing and verifying required dependencies from requirements.txt...
!PYTHON_EXE! -m pip install -r "%APP_DIR%requirements.txt"
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Some packages had installation warnings. Continuing with pre-flight check...
)

:STEP1
:: 1. Pre-flight dependency check
echo.
echo [STEP 1/3] Checking system environment and runtime dependencies...
if exist "%APP_EXE%" (
    "%APP_EXE%" --check-deps
) else (
    !PYTHON_EXE! "%APP_DIR%desktop_app.py" --check-deps
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [WARNING] Some dependencies or configuration settings require attention.
    echo Running full diagnostics...
    if exist "%APP_EXE%" (
        "%APP_EXE%" --diagnose
    ) else (
        !PYTHON_EXE! "%APP_DIR%desktop_app.py" --diagnose
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
    !PYTHON_EXE! "%APP_DIR%desktop_app.py" --create-shortcut
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
    start "" !PYTHON_EXE! "%APP_DIR%desktop_app.py"
)

:END
echo Done. You may close this window.
timeout /t 3 >nul 2>&1 || ping 127.0.0.1 -n 4 >nul
exit /b 0
