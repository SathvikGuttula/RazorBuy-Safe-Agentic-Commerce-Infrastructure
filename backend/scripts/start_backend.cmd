@echo off
set "BACKEND_ROOT=%~dp0.."
"%BACKEND_ROOT%\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8000
