@echo off
setlocal

set "PROJECT_ROOT=E:\POS\KASIR"
set "POS_PROJECT_ROOT=E:\POS\KASIR"
set "OPENCODE_DB=%USERPROFILE%\.opencode-data\opencode.db"

if not exist "%USERPROFILE%\.opencode-data" (
    mkdir "%USERPROFILE%\.opencode-data"
)

if not exist "%PROJECT_ROOT%\venv\Scripts\python.exe" (
    echo ERROR: Python venv tidak ditemukan.
    echo Periksa folder %PROJECT_ROOT%\venv
    pause
    exit /b 1
)

if not exist "%PROJECT_ROOT%\mcp_server\server.py" (
    echo ERROR: MCP server tidak ditemukan.
    pause
    exit /b 1
)

cd /d "%PROJECT_ROOT%"

echo Memulai OpenCode untuk proyek POS...
echo Project: %PROJECT_ROOT%
echo MCP Python menggunakan venv proyek.
echo.

opencode

echo.
echo OpenCode telah berhenti.
pause

endlocal
