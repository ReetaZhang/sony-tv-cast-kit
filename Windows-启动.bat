@echo off
rem Sony TV Cast Kit - launcher for Windows
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "installer\main.py"
    goto :end
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "installer\main.py"
    goto :end
)

echo.
echo Python 3 was not found on this computer.
echo Install it from https://www.python.org/downloads/ and run this file again,
echo or install the receiver APK from a USB drive instead.
echo.
pause

:end
