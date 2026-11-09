@echo off
title Stock Intelligence Launcher
echo ================================================================
echo   STOCK INTELLIGENCE PRO - LOCAL DEV LAUNCHER
echo ================================================================
echo.
echo Starting FastAPI Backend on http://127.0.0.1:8000 ...
start "Stock Intelligence Backend (8000)" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

echo Starting Vite React Frontend on http://localhost:5173 ...
start "Stock Intelligence Frontend (5173)" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ================================================================
echo   SERVICES LAUNCHED!
echo   * Frontend URL:   http://localhost:5173
echo   * Backend URL:    http://127.0.0.1:8000
echo   * API Docs:       http://127.0.0.1:8000/docs
echo ================================================================
echo You can keep this window open or close it. The service windows
echo will stay running.
pause
