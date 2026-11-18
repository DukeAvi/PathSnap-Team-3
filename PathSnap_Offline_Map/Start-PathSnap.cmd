@echo off
setlocal
cd /d "%~dp0" || goto :failed

if exist ".venv\Scripts\python.exe" goto :install
py -3.12 -m venv .venv
if errorlevel 1 (
    echo Python 3.12 is required. Run: winget install --id Python.Python.3.12 --exact
    goto :failed
)

:install
if exist ".venv\.pathsnap-ready" goto :run
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
type nul > ".venv\.pathsnap-ready"

:run
echo.
echo Open http://127.0.0.1:8010 after Uvicorn starts.
echo.
".venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8010
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo PathSnap could not start. See the error above.
pause
exit /b 1
