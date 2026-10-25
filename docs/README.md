# Rahat documentation and operations guide

This is the detailed guide for the canonical Rahat implementation. The
shorter project overview and copy/paste commands are in the root
[../README.md](../README.md).

## Submission Reading Guide

Start with [../README.md](../README.md), then read
[ARCHITECTURE.md](ARCHITECTURE.md), [TECHNOLOGY.md](TECHNOLOGY.md) and
[LIMITATIONS.md](LIMITATIONS.md). The root
[../AI_USAGE.md](../AI_USAGE.md) names every runtime AI producer and consumer,
and separates decision-affecting output from explanation-only features.

For running and presenting the build, use [SETUP.md](SETUP.md),
[DEMO.md](DEMO.md) and [CHECKLIST.md](CHECKLIST.md). Measured results are in
[AI_EVALUATION.md](AI_EVALUATION.md); source/licence/snapshot status is in
[DATA_SOURCES.md](DATA_SOURCES.md).

[AI_BRIEF.md](AI_BRIEF.md) is the design brief, not an implementation report.
The older agent design in [AGENTS.md](AGENTS.md) is historical: its tool loop,
auto-dispatch settings, embeddings and gateway paths are not current features.

## 1. Runtime architecture

Rahat has one operational backend and two separate frontends:

```text
Public/mobile Flutter app (frontend/)
  SOS, Direct SOS, profiles, volunteers, help offers, mesh retry
                 |
                 | HTTP / JSON, durable client UUIDs, receipt tokens
                 v
Canonical FastAPI backend (backend/)
  auth, SOS, incidents, needs, volunteers, assignments,
  notifications, resources, routing, audit, AI and migrations
                 |
                 +--> SQLite database (backend/relief.db)
                 +--> local Ollama (optional, qwen2.5:3b)
                 ^
                 |
Service Station Flutter web app (station/)
  live Nepal map, SOS queue, state machine, dispatch, ledger,
  hazards/routes, AI proposals, coverage and resilience controls
```

The Service Station is a control hub over the same backend. It must not create
or maintain a separate incident database. A request received by `/sos` is the
same request shown to an authenticated coordinator in the Service Station.

Legacy experiments are outside the canonical runtime. The maintained public
app and Service Station use the same backend rather than a legacy gateway.

## 2. Project structure

```text
backend/
  app/main.py                    FastAPI app, CORS, health and static hosting
  app/models.py                  SQLAlchemy models and operational constraints
  app/schemas.py                 Pydantic API validation
  app/routers/auth.py            Login, registration, profile and roles
  app/routers/sos.py             SOS intake, receipt, location and transitions
  app/routers/command_station.py Shared control-hub API under /api/v1
  app/routers/assignments.py     Volunteer matching and assignment actions
  app/routers/resources.py       Allocation, dispatch and receipt evidence
  app/routers/routing.py         Routes and verified road hazards
  app/services/                  Notifications, scheduling and SOS processing
  alembic/versions/              Data-preserving database migrations
  tests/                         Backend and AI workflow tests

frontend/
  lib/screens/home.dart           Public home and Direct SOS entry
  lib/screens/sos.dart            Structured help request
  lib/screens/direct_sos.dart     One-confirmation emergency flow
  lib/screens/map.dart            Offline Nepal map and real SOS markers
  lib/api.dart                    Durable outbox, receipts and GPS enrichment
  lib/mesh_service.dart           Network retry and BLE relay orchestration
  lib/screens/coordination.dart   Shared coordination widgets used by station
  assets/                         Nepal provinces and district headquarters
  android/                        Native Android application and BLE support

station/
  lib/main.dart                   Separate Service Station entry point
  assets/                         Map assets bundled for station web
  pubspec.yaml                    Depends on shared frontend coordination code

ai/
  coordinator.py                  Database-backed coordination proposals
  client.py                       Ollama calls, timeouts and JSON generation
  sos_tasks.py                    SOS interpretation; calls notification service
  report_tasks.py                 Report parsing and need extraction
  volunteer_tasks.py              Controlled skill mapping and reasoning
  resource_tasks.py               Allocation reasoning
  road_tasks.py                   Road and hazard reasoning
  schemas.py                      AI output contracts

protocol/                         Signed relay packet support
docs/                             This guide and specialized documentation
miscellaneous/                    Legacy/non-runtime material
```

## 3. Startup and port management

### Backend

```powershell
Set-Location 'D:\Rahat final\backend'
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe -m app.setup_local --demo
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Use `app.setup_local` after pulling schema changes. It applies migrations,
including the SOS reporter-column repair, without deleting existing data.

### Public/mobile app

```powershell
Set-Location 'D:\Rahat final\frontend'
flutter pub get
flutter run -d chrome --web-port 52394
```

Use the Android build for native GPS/BLE testing:

```powershell
flutter build apk --debug
```

### Service Station

```powershell
Set-Location 'D:\Rahat final\station'
flutter pub get
flutter run -d web-server --web-hostname 127.0.0.1 --web-port 52396
```

Open `http://localhost:52396`. `web-server` mode is preferred on this Windows
machine because Chrome debug attachment can time out. Keep its terminal open.

Expected local addresses:

```text
Backend:         http://127.0.0.1:8000
Mobile frontend: http://localhost:52394
Service Station: http://localhost:52396
```

If Flutter reports `10048`, a server is already listening on that port. Use
the existing URL or inspect the owner:

```powershell
Get-NetTCPConnection -LocalPort 52394,52396,8000 -State Listen
Get-Process -Id <OwningProcess>
```

If restarting, stop only the exact process ID:

```powershell
Stop-Process -Id <OwningProcess>
```

Do not start the legacy gateway from the preserved repository beside the
canonical backend.

## 4. Service Station operations

After coordinator sign-in, the station displays the live Nepal operations map
above the operational tabs. Map markers are loaded from the authenticated
shared SOS feed and missing coordinates are not fabricated.

The station provides:

1. **Reliable flow** — SOS persistence, receipt confirmation, queue loading,
   notification fan-out and refresh.
2. **Incident state machine** — `received`, `acknowledged`, `verified`,
   `awaiting_dispatch`, `assigned`, `responding`, `on_scene`, `resolved`,
   and `cancelled`. Valid transitions and audit entries are enforced in the
   backend.
3. **Volunteer dispatch** — eligibility, skills, availability, travel range,
   invitation waves, confirmation, ETA comparison, reservation and fallback.
4. **Resource ledger** — requested, allocated, dispatched, received,
   remaining, reconciliation and duplicate-confirmation handling.
5. **Map/routing** — offline Nepal map, coordinates, route estimates,
   alternative routes, verified hazards, freshness labels and route-change
   notices. Unverified hazards are not treated as road closures.
6. **AI coordination** — database-backed proposals, intelligence, drafts,
   confidence and fallback status. Human approval is required for consequential
   actions.
7. **Resilience/insights** — coverage, bottlenecks, notifications, mesh
   simulation, retry visibility and operational summaries.

Relevant API groups:

```text
/api/v1/health
/api/v1/incidents
/api/v1/incidents/{id}/transition
/api/v1/incidents/{id}/dispatch-wave
/api/v1/incidents/{id}/resource-ledger
/api/v1/incidents/{id}/routes
/api/v1/road-hazards
/api/v1/coverage
/api/v1/coordinate
```

The legacy pulled dashboard contained useful map and queue presentation, but
its sample fallback and old gateway routes were not copied as production truth.
The maintained station uses real authenticated canonical APIs and keeps AI and
delivery claims evidence-based.

## 5. End-to-end SOS behavior

```text
User presses Direct SOS or submits structured SOS
  -> request is saved locally with client_uuid
  -> HTTP POST /sos
  -> SOSEvent is committed to relief.db
  -> receipt_token confirms backend persistence
  -> background AI interpretation starts
  -> coordinator/high-priority volunteer/contact notifications are created
  -> Service Station queue refreshes or receives the event
  -> coordinator verifies, assigns, dispatches and records evidence
```

Network failure does not discard the request. The same UUID remains in the
outbox and is retried. A receipt confirms server persistence only; it does not
claim dispatch, arrival, or delivery.

Written location fields are preserved as structured address data. GPS is
optional, measured separately, and may later enrich a received SOS. No GPS is
invented from an address or replaced with a default Kathmandu coordinate.

Direct SOS has one confirmation on its dedicated page and then uses HTTP,
durable retry, and native BLE relay where supported. Browser builds clearly
state when Bluetooth is unavailable.

## 6. AI implementation and guardrails

### Inputs and interpretation

The AI can interpret short or incomplete English, Nepali, and Romanized Nepali
reports. It extracts structured fields such as:

- location text and known coordinates
- affected people/families
- needs, categories, quantities and units
- urgency and vulnerable groups
- hazards and required skills
- missing information and follow-up questions
- duplicate/report similarity signals

### Coordination

The backend first supplies real candidates and state. Deterministic code checks
permissions, verified skills, availability, workload, capacity, travel
feasibility, route hazards, stock and receipt state. Ollama may then rank or
explain those allowed options and create a structured draft proposal.

The model cannot directly:

- change incident or assignment states
- reserve or consume stock
- mark supplies dispatched or received
- invent a road closure, route, coordinate, skill or quantity
- bypass role permissions
- claim an SOS was delivered

Every proposal is reviewable. Coordinator approval is required for
assignments, allocations, dispatches and other irreversible actions.

### Ollama and fallback

```text
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
```

When Ollama is unavailable, structured deterministic fallback logic keeps SOS
intake, database persistence, notification escalation, matching safeguards and
resource accounting working. Fallback output is labelled; it is never
presented as model confidence.

See [../AI_USAGE.md](../AI_USAGE.md) for the public usage
disclosure and [AI_EVALUATION.md](AI_EVALUATION.md) for
evaluation procedures.

## 7. Database, security and evidence

- Run Alembic migrations through `app.setup_local`.
- Keep `backend/.env` private; never commit JWT or Twilio credentials.
- SOS client UUIDs make retries idempotent.
- Receipt tokens protect later GPS/status updates.
- Role checks protect station and coordinator actions.
- Audit entries record state changes and AI decisions.
- Resource receipts are separate evidence from dispatch.
- Emergency-contact fan-out is scoped to the authenticated reporter.
- SMS is disabled unless Twilio credentials are configured; no fake success is
  returned.

Detailed references:

- [DATABASE.md](DATABASE.md)
- [AUTH_SECURITY.md](AUTH_SECURITY.md)
- [ANDROID_BLE.md](ANDROID_BLE.md)
- [API.md](API.md)

## 8. Validation commands

```powershell
# Backend
Set-Location 'D:\Rahat final\backend'
..\.venv\Scripts\python.exe -m pytest

# Public/mobile frontend
Set-Location 'D:\Rahat final\frontend'
flutter analyze
flutter test

# Service Station frontend
Set-Location 'D:\Rahat final\station'
flutter analyze
flutter test
flutter build web
```

The current focused validation covers database workflows, migrations, SOS
receipts, retries, profiles, notifications, resource partial receipts,
coordination roles, map assets, and Service Station loading.

## 9. Honest limitations

- Web browsers do not provide the native BLE relay path.
- Background retry requires the app page to remain open or be reopened.
- GPS accuracy depends on device permission and hardware.
- Route results are estimates unless a verified routing provider is installed.
- Exact SOS coordinates are restricted to authorized operational views.
- AI cannot replace human verification or emergency-service dispatch.
- Nepal emergency phone numbers require actual phone/network coverage.

See [LIMITATIONS.md](LIMITATIONS.md) before public
demonstrations.
