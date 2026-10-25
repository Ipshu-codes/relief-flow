# Rahat Service Station frontend

Separate Flutter web frontend for authorized coordinators. It is the control
hub over the same backend and database used by the public/mobile app.

## Includes

- Live Nepal operations map above the station workspace
- Real authenticated SOS queue and severity markers
- Incident state machine and audit-aware actions
- Volunteer eligibility, dispatch waves, confirmations and fallback
- ETA comparison, assignments and notifications
- Resource ledger and evidence-backed receipts
- Routes, verified hazards, freshness and route-change context
- Ollama AI status, intelligence, proposals and human approval
- Coverage, bottleneck, mesh and resilience tools

## Run

```powershell
Set-Location 'D:\Rahat final\station'
flutter pub get
flutter run -d web-server --web-hostname 127.0.0.1 --web-port 52396
```

Open `http://localhost:52396`. Keep the terminal open. `web-server` mode is
preferred when Chrome debug attachment times out.

The backend must be running at `http://127.0.0.1:8000`. Sign in using a
coordinator account. The station does not own a separate database.

Tests and release web build:

```powershell
flutter analyze
flutter test
flutter build web
```
