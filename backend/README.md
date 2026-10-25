# Rahat canonical backend

This directory contains the shared FastAPI backend used by both the public
Flutter app and the separate Service Station frontend.

## Run

```powershell
Set-Location 'D:\Rahat final\backend'
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe -m app.setup_local --demo
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Health: `http://127.0.0.1:8000/api/health`  
OpenAPI: `http://127.0.0.1:8000/docs`  
Service Station health: `http://127.0.0.1:8000/api/v1/health`

## Responsibilities

- Authentication, roles, profiles and emergency contacts
- Idempotent SOS intake, receipts, state transitions and audit trail
- Incidents, needs, volunteers, organizations and assignments
- Dispatch waves, fallback, ETA and eligibility enforcement
- Resource allocation, dispatch, receipt evidence and reconciliation
- Routing estimates, verified road hazards and coverage reports
- Notification fan-out and offline synchronization
- Ollama-backed structured AI proposals with deterministic safeguards

The backend is the only operational store. Do not run the preserved legacy
gateway beside it. See [`../docs/README.md`](../docs/README.md).
