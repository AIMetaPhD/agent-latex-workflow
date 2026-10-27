@echo off
setlocal EnableExtensions
rem ---------------------------------------------------------------------------
rem Launch the Local Companion UI on Windows.
rem Resolves the project root from THIS FILE's location, not the current
rem directory, so a double-click from anywhere works.
rem Tries `py -3` first (the Python launcher), then a real `python`, and skips
rem the Microsoft Store alias that otherwise opens the Store instead.
rem ---------------------------------------------------------------------------

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

set "PY="

rem 1) the Python launcher, if present
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
    if not errorlevel 1 set "PY=py -3"
)

rem 2) a python that is NOT the WindowsApps Store alias
if not defined PY (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        echo %%P | findstr /i "WindowsApps" >nul
        if errorlevel 1 (
            if not defined PY set "PY=%%P"
        )
    )
)

if not defined PY (
    echo.
    echo   Python 3.10 or newer was not found.
    echo.
    echo   Install it with one of these, then run this file again:
    echo       winget install --id Python.Python.3.12 -e
    echo       https://www.python.org/downloads/
    echo.
    echo   If Python is installed but only as the Microsoft Store alias,
    echo   turn off "App execution aliases" for python.exe in Windows Settings.
    echo.
    pause
    exit /b 1
)

echo Starting the paper workbench from "%ROOT%" ...
%PY% "%ROOT%\ui\server.py" %*
if errorlevel 1 (
    echo.
    echo   The workbench stopped with an error. The message above says why.
    echo.
    pause
)
endlocal
