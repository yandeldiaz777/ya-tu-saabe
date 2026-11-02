@echo off
cd /d "%~dp0"
where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw -3 "%~dp0windows_ui.py"
) else (
    py -3 "%~dp0windows_ui.py"
    if errorlevel 1 pause
)
