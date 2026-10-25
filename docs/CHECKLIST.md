# Submission Checklist

This checklist separates implemented code from submission evidence. Checked
implementation items do not certify live model quality or production safety.
Review date: 25 October 2026.

## Required Documentation

- [x] [../README.md](../README.md): problem, workflow, diagram, stack, setup,
  model install, tests, evaluation results, sources, limits and next steps.
- [x] [ARCHITECTURE.md](ARCHITECTURE.md): shared records, AI boundaries and failure paths.
- [x] [TECHNOLOGY.md](TECHNOLOGY.md): current runtime choices, not legacy dependencies.
- [x] [LIMITATIONS.md](LIMITATIONS.md): known risks and future improvements.
- [x] [../AI_USAGE.md](../AI_USAGE.md): exact model-call and output-consumer functions.
- [x] [SETUP.md](SETUP.md): fresh-install and local-run instructions.
- [x] [AI_EVALUATION.md](AI_EVALUATION.md): measured results, coverage and failures.
- [x] [DATA_SOURCES.md](DATA_SOURCES.md): source, licence and snapshot-date status.
- [x] [DEMO.md](DEMO.md): four-minute script and presentation outline.

## Submission Gates Still Requiring Evidence

- [ ] Confirm the repository is publicly accessible and can be installed
  from a clean checkout without private assets or credentials.
- [ ] Confirm the organizer's current rules, including AI coding assistance
  and the build brief's "AI cannot simply be removed" requirement.
- [ ] Obtain completed live `source=ai` responses and a matched quality
  comparison. Current measurements do not prove an AI advantage.
- [ ] Rehearse the current build end to end and record a demo or presentation.
- [ ] Add the actual public repository and recording/presentation URLs to
  the submission. No video URL is available in this documentation update.
- [ ] Complete licence/provenance records for redistributed datasets and
  remove private data, local databases and secrets from public artifacts.

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

## Previously Recorded Validation

The results below are retained from the earlier implementation notes. They
were **not rerun as part of this documentation update** and should not be
treated as current suite counts. Re-run the commands in [SETUP.md](SETUP.md)
before recording or submitting a changed build.

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

## Build Brief Gaps

| Requirement | Current Status |
|---|---|
| Shared records, schema wrapper, retry and labelled fallback | Implemented |
| Thirty-message evaluation corpus and baseline | Present; keyword exact-category score is 20/30 |
| Three-model accuracy/latency comparison | Not completed; all five recorded live 3B cases fell back after timeouts |
| Real district census, ward boundaries and facilities | Import support is not a completed, audited district dataset |
| External feeds with offline snapshots | Open-Meteo implements saved-response fallback; do not generalize this to all BIPAD/DHM feeds |
| Parsed road notices | Implemented with human verification; road-network navigation remains absent |
| Skill, assignment and stock choices | Implemented with code-owned feasibility and human approval |
| General coordinator tool registry and recurring AI loop | Not implemented; current cycle selects assignment/allocation drafts |
| Duplicate judgment | Stored as flag evidence; automatic report merging is not implemented |
| Bottleneck explanation | Returned on request; suggested text does not automatically trigger actions |
| Outcome-driven learning and confidence auto-approval | Not implemented |
| Retrieval / open-model embeddings | Not implemented; stretch work |
| Demo video | Script provided; recording still required |

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
