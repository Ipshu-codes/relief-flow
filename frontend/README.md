# Rahat public/mobile frontend

Flutter application for people requesting help and people offering help.

## Features

- Structured SOS and one-confirmation Direct SOS
- Durable offline SOS outbox and receipt-aware retry
- Written Nepal locations and optional GPS enrichment
- Nepal emergency calling shortcuts
- Volunteer and organization registration
- Community help offers and notifications
- Status tracking, profiles and emergency contacts
- Offline map, mesh simulation and native Android BLE relay

The Service Station is intentionally a separate frontend in
[`../station/`](../station).

## Run

```powershell
Set-Location 'D:\Rahat final\frontend'
flutter pub get
flutter run -d chrome --web-port 52394
```

The backend should be running at `http://127.0.0.1:8000`. Users do not enter
that address; local debug URL resolution handles it automatically.

Android build:

```powershell
flutter build apk --debug
```

Tests:

```powershell
flutter analyze
flutter test
```
