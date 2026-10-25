# Rahat: unified local-AI relief coordination

Rahat helps communities submit emergency requests and helps human coordinators
match verified volunteers and supplies to needs. It is a coordination prototype,
not a certified emergency dispatch service.

## Canonical project

```
backend/       FastAPI, JWT auth, models, services, migrations and tests
               |-- /api/v1 Command Station: incidents, state machine, dispatch,
               |--     resource ledger, road hazards, AI coordination, coverage
frontend/      Flutter app: public SOS and authenticated response workspace
ai/            Local Ollama wrapper, validated schemas and versioned prompts
protocol/      Signed RMP codec inherited from the original platform
docs/          Submission materials and build briefs
miscellaneous/ Preserved older implementations; excluded from submission
```

The original `Rahat-A-disaster-response-platform/` remains intact as requested.
Do not start its older gateway alongside the canonical backend on port 8000.
Existing historical databases are preserved, not automatically merged: their
incident models differ. New SOS, volunteers, needs and assignments now use the
same canonical database.

## Prerequisites

- Windows PowerShell, Python 3.11+, Flutter 3.24+ with Chrome for web.
- Ollama and the local `qwen2.5:3b` model for actual AI inference. With Ollama
  unavailable, resilient intake and explicitly labelled fallback recommendations
  still work. Inference quality must not be confused with the unit test results.

Run all following commands from the project root:

```powershell
Set-Location 'D:\Rahat final'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e . -r backend\requirements.txt
.\.venv\Scripts\python.exe -m app.setup_local --demo
ollama pull qwen2.5:3b
Set-Location frontend
flutter pub get
flutter build web
Set-Location ..
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/**. API docs: **http://127.0.0.1:8000/docs**.
Health: `/api/health`; local model availability: `/ai/status`; command station health: `/api/v1/health`.

### SOS location and emergency calls

- Rahat supports both sides of a response. **I need help** opens the SOS and
  need-reporting flow. **I can help** opens volunteer registration, nearby
  community help offers, and responder assignments. A volunteer's home/usual
  response area is optional matching context, not an employer or incident
  assignment. Skills, proficiency, languages, equipment, availability, and
  organization membership remain separate fields.
- Signed-in users can offer water, food, medicine, transport, shelter, or
  skilled help from the **Help nearby** tab. Offers are persisted, can be
  claimed by another user, and create in-app notifications for coordinators
  and the offer owner. Claiming an offer is a coordination response, not an
  automatic deployment or proof of delivery.
- SOS alerts create in-app notifications for coordinators and, for priority
  4–5 reports, available volunteer profiles. Consented emergency contacts are
  matched to a Rahat account by phone number for in-app alerts and are also
  sent an SMS when the Twilio adapter is configured. Without SMS credentials,
  the SOS is still saved and the in-app fan-out still works; no fake SMS
  success is reported.
- Signed-in users can open **Emergency profile** from Settings or the
  Coordination screen to save their phone number, a structured written home
  location, optional measured coordinates, accessibility/medical notes, and up
  to five trusted emergency contacts. Contacts are separate from responders
  and official emergency services; each contact records whether location may
  be shared and whether notifications are permitted. Incomplete contact
  records are rejected.
- If GPS is unavailable, enter any known **district > city/municipality/village >
  ward > road/tole**, plus a nearby **school, hospital or other landmark**.
  Unknown fields can be left blank. Text is stored as a structured address, not
  guessed coordinates, and is shown in the coordinator's SOS queue.
- Sending saves the entire request locally before attempting the network.
  With the SOS screen open, pending requests retry every 20 seconds and on app
  resume using the same request UUID, including the written address.
- With "Share GPS when available" enabled and location permission granted, GPS
  can be acquired without internet. The SOS/status screen sends missing GPS
  after connectivity returns. A receipt-protected location update enriches an
  already received request without replacing its written address or creating
  another SOS. GPS accuracy and update time remain visible to the coordinator.
  A later GPS fix is the device's **current** position, not necessarily the
  original incident location; no "exact" accuracy is promised.
- Automatic retries require the app screen to remain open (or be reopened);
  closed-browser background delivery is not implemented. Web GPS requires a
  secure origin (HTTPS or localhost). No GPS is fabricated from text.
- The Command Station includes an offline Nepal basemap with province
  boundaries and district headquarters. Authenticated station users see real
  SOS coordinates as severity-coloured markers; missing coordinates are not
  plotted. The map is a basemap and operational overlay, not proof of a live
  road route or hazard.
- The Service Station is the **Response** area in the Flutter app, or the
  `/coordination` route. A coordinator signs in there to see the shared SOS
  queue, Nepal Map, incident transitions, notifications, dispatch, and
  resource ledger. It is not a second server or database: it reads the same
  backend at `http://127.0.0.1:8000` during local development.
- If an existing local database was created before a schema update, run
  `python -m app.setup_local` from `backend` before starting Uvicorn. This
  applies all migrations, including the SOS reporter identity repair; without
  it the browser can show an unhandled Dart promise because `/sos` returns
  HTTP 500.
- The home screen's **DIRECT SOS** action requires confirmation, sends the
  minimum emergency request over the configured backend first, then retains
  the same request in the phone queue when the network is unavailable. Native
  Android devices can relay that queued request through the BLE mesh; web
  builds report that Bluetooth is unavailable rather than claiming delivery.
- Emergency call buttons directly below SOS open the device's calling app with
  `tel:100` (police), `tel:102` (ambulance), `tel:101` (fire) or `tel:1144`
  (tourist police). The user confirms the call in their phone app. Numbers are
  **Nepal-only**; coverage and phone service are required. No real emergency
  calls are placed during testing. Unsupported devices show the number to dial.
  Source: [FCDO Nepal emergency services](https://www.gov.uk/foreign-travel-advice/nepal/getting-help).
  Ambulance coverage is not universal; contact a nearby hospital if unavailable.

Written addresses also survive authenticated gateway `/sync/sos-batch` intake
with `channel: mesh`. This is the supported bridge/API contract, **not proof of
phone-to-phone Bluetooth delivery**. The browser has no working physical mesh
transport, and the older 200-byte signed RMP format cannot carry an arbitrarily
long structured address. Its compact text may be truncated. The Mesh Lab is
explicitly a simulation; real offline radio relay needs tested native hardware,
fragmentation and reassembly before it can be relied upon.

Convenience alternative once Python/Flutter are on PATH:

```powershell
.\start.ps1 -Setup -Demo -Build
```

Subsequent runs: `.\start.ps1`. Rebuild web after Flutter source edits and restart
the backend after the first build so static files are mounted.

### Development frontend

```powershell
Set-Location frontend
flutter run -d chrome --web-port 3000
```

Localhost debug previews (including VS Code's random ports) automatically use
the backend on port 8000. Release web builds use their serving origin, including
custom ports; host the frontend and API together or reverse-proxy API routes.
SOS, registration and sign-in all use this same deployment configuration.
Users never enter a server address, and old saved address overrides are cleared.

### Separate mobile app and Service Station frontends

The public responder app and the Service Station are separate frontends:

- `frontend/` is the Flutter mobile/public app for people requesting help,
  volunteers, profiles, emergency contacts, Direct SOS, mesh relay, and
  offline operation.
- `station/` is a separate Flutter web frontend for coordinators. It reuses
  the tested coordination screens and Nepal Map assets from the mobile package,
  but has its own app entry point and browser build. It does not create a
  second database.
- The preserved original repository used the same separation as `mobile/` and
  `dashboard/`; the current `station/` frontend is the maintained equivalent
  wired to the canonical backend rather than the legacy gateway.

Run them independently:

```powershell
# Backend
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Public/mobile web preview
Set-Location frontend
flutter run -d chrome --web-port 52394

# Service Station web preview (use another available port)
Set-Location station
flutter run -d chrome --web-port 52396
```

Both frontends use the same backend and database. Sign in to the Service
Station with a coordinator account; the station then provides the SOS queue,
Nepal Map, incident transitions, dispatch, notifications, and resource
coordination.

### Command Station control-hub workflow

The Command Station is an authenticated coordination layer over the same
backend database as the public app; it is not a second SOS store. A received
SOS is persisted first, then appears in the station's queue and notification
fan-out. Coordinators inspect the written address and measured coordinates,
verify the request, match eligible volunteers, dispatch supplies, and record
evidence-backed outcomes.

Incident transitions are controlled and audited:

```
received -> acknowledged -> verified -> awaiting_dispatch -> assigned
          -> responding -> on_scene -> resolved
```

`cancelled` is available from any non-terminal state. Every transition is
written to the shared audit log. The `/api/v1/command-station` endpoints expose
the station queue, state transitions, volunteer matching/assignment, resource
progress, coverage insights, route/hazard context, and coordination-cycle
recommendations. AI recommendations are structured proposals only; database
permissions, volunteer capacity, assignment transitions, route hazard
verification, and delivery receipts remain deterministic backend decisions.

Supply progress distinguishes allocated, dispatched, received, and remaining
quantities. A receipt is never inferred from dispatch: a receiving user must
confirm the quantity, and duplicate confirmation UUIDs are reported as
duplicates. Road closures are only used after coordinator verification and
carry freshness/expiry metadata. If Ollama or the network is unavailable,
fallback rules preserve intake and critical escalation without inventing
facts, delivery, or road hazards.

For a separately hosted frontend or native app, the **developer** sets the address
at launch/build time, for example:

```powershell
flutter run --dart-define=BACKEND_BASE_URL=http://10.0.2.2:8000
flutter build web --dart-define=BACKEND_BASE_URL=https://api.example.org
```

The first example is for an Android emulator. For a physical phone bind the
backend intentionally to `0.0.0.0`, build with the computer's LAN address and configure
firewall/CORS appropriately. Never expose the public demo accounts to a network
you do not trust. Loopback on a phone means the phone, not your laptop.

## Database and configuration

`backend/.env.example` documents configuration. `app.setup_local` generates a
local JWT secret in private `backend/.env` if missing and runs the Alembic
data-preserving adoption migration. SQLite defaults to `backend/relief.db`.
Relative SQLite paths resolve from `backend/`, not the shell working directory.
Repeat setup safely; seed records are not duplicated. Back up any real database
before migrating. The migration adopts the existing module schema and adds
volunteer contact information; it is not a general migration from the separate
legacy gateway database.

Without public demo data:

```powershell
.\.venv\Scripts\python.exe -m app.setup_local
.\.venv\Scripts\python.exe -m app.bootstrap_admin operator@example.org
```

Bootstrap prompts for the administrator's name and password without storing
plaintext credentials. Signed JWTs expire; sign in again after expiry. Frontend
JWTs stay in memory, not local storage. SOS receipts are local bearer capabilities
that reveal only limited delivery status.

### Local demo accounts

Created only by explicit `--demo`:

| Account | Password | Role |
|---|---|---|
| coordinator@demo.rahat.org | RahatDemo2026! | Coordinator |
| volunteer@demo.rahat.org | RahatDemo2026! | Volunteer |

Synthetic locations and requests are labelled `[DEMO]`. Self-registering a
community user never grants coordinator/admin rights. Organization registration
grants only scoped organization administration; employees start with unverified
skills until an authorized manager verifies them.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
Set-Location frontend
flutter test
flutter analyze
flutter build web
```

See [AI evaluation](AI_EVALUATION.md) for measured model/fallback evaluation and
the separate live-model command. Unit tests deliberately disable inference;
specific tests supply schema-valid or invalid mock outputs.

## Submission materials

- [Architecture](ARCHITECTURE.md)
- [Technology](TECHNOLOGY.md)
- [Feature integration inventory](INTEGRATION.md)
- [AI architecture and programmatic-use disclosure](AI_USAGE.md)
- [Demo runbook and recording outline](DEMO.md)
- [Limitations and next steps](LIMITATIONS.md)
- [Requirements checklist](CHECKLIST.md)

No model binaries, local secrets, generated builds, caches or local databases
should be committed. Include source, manifests, lockfiles, migrations, tests,
prompts and the protocol package. The source can rebuild the Flutter web output.
