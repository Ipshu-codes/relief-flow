# Submission checklist

## Completed implementation

- [x] Inspect existing projects, reuse module backend authentication and services.
- [x] Canonical backend/frontend/ai/docs organization; preserve original platform.
- [x] Import/package references and editable installation updated.
- [x] Shared SOS/needs/volunteers/assignments/stock database.
- [x] Data-preserving Alembic initialization and repeated setup.
- [x] JWT login, community registration and role-scoped routes.
- [x] Public SOS, honest GPS/manual/unavailable location, durable UUID retry.
- [x] Nested written address and landmark, preserved offline and in gateway batches.
- [x] Foreground SOS retry and receipt-protected later GPS enrichment.
- [x] Nepal emergency call links below SOS, with unsupported-device error feedback.
- [x] Automatic deployment connection; no API address in sign-in, registration or settings.
- [x] Limited receipt-token status and coordinator queue/ack/dispatch/resolve.
- [x] Individual volunteer and organization employee registration, multiple skills.
- [x] Authorized skill verification, availability and travel requirements.
- [x] AI-backed candidate proposals and human approval.
- [x] Command Station: incident state machine, dispatch waves, resource ledger, road hazards, AI coordination, WebSocket stream, coverage analytics.
- [x] Supply reservation and partial confirmed-receipt progress.
- [x] Intelligence/baseline/blockage/bottleneck/recovery UI wired to existing services.
- [x] Original signed RMP codec ingestion into the same receiver.
- [x] Labelled Mesh Lab bridge queue-and-reconnect simulation.
- [x] Original dark colors with a simpler public emergency interface.
- [x] Setup/runbook, architecture, technology, limits, AI disclosure and demo outline.

## Validation

- Backend: `python -m pytest backend\tests -q --tb=short`: **32 passed**;
  one existing Starlette/httpx deprecation warning.
- Frontend: `flutter test`: **35 passed**; `flutter analyze`: **no issues**;
  `flutter build web --no-wasm-dry-run`: **succeeded**.
- Dart Tooling Daemon: hot reload and final hot restart **succeeded**.
- Browser: production build exercised on an isolated demo database at port 8011.
  A no-GPS SOS with district/city/ward/road/landmark returned HTTP 201; the
  coordinator queue displayed the saved address and acknowledgement returned
  HTTP 200. Status showed the acknowledgement. A **simulated browser GPS fix**
  automatically enriched the same SOS with HTTP 200 and showed confirmation.
  This does not certify GPS hardware, radio transport or an emergency phone call.
- Persistent canonical server: `.\start.ps1` serves `/` and `/api/health` at
  port 8000; migration columns verified on the local database without resets.

See the AI evaluation report for measured model behavior.
Do not equate implementation or mocked/simulated tests with deployment certification.

## Explicitly incomplete / out of scope for this submission

- [ ] Physical BLE/Meshtastic/LoRa end-to-end transport and hardware ACKs.
- [ ] Verified road-network routing or offline map tile package.
- [ ] Production PostgreSQL/PostGIS/concurrent-load certification.
- [ ] Verified district-wide government datasets and complete source licensing.
- [ ] All-model 30-message comparative benchmark (only claim measured coverage).
- [ ] Full Nepali UI and Nepali-script accuracy certification.
- [ ] Recorded demo video (recording outline provided).
- [ ] Production operational/security review and emergency-service certification.

These are documented limits, not hidden completed checkboxes.
