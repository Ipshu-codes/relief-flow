# Canonical backend

See [complete setup](../docs/README.md). Run from the project root:

```powershell
.\.venv\Scripts\python.exe -m pip install -e . -r backend\requirements.txt
.\.venv\Scripts\python.exe -m app.setup_local --demo
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The backend and built Flutter app share port 8000 and a single module database.
AI lives in the root `ai/` package. Tests: `python -m pytest backend\tests -q`.
Private configuration is `backend/.env`; use `.env.example` as reference.
