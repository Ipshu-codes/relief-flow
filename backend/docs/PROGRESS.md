# RAHAT Backend Development Progress

**Component:** Backend REST API and AI coordination layer
**Status:** Authentication, Phase 0.4 report intake, and Modules 1–3 backend workflows are implemented; Phase 0.5 coordinator proposals remain.

## 1. Project Overview

RAHAT is a disaster-response coordination backend for Nepal. The backend supports skilled-volunteer coordination, disaster intelligence and feedback, and offline SOS relay synchronization. AI interprets reports and proposes actions; application code validates business rules, and authorized people approve operational changes.

## 2. Technologies

- Python 3.11+
- FastAPI and Pydantic v2
- SQLAlchemy 2 and SQLite
- Alembic migrations
- JWT bearer authentication and Argon2 password hashing
- Ollama as an optional local AI service
- pytest and HTTPX

## 3. Current Progress

### Foundation and Authentication

- [x] Added environment-backed SQLite configuration and Alembic migration setup.
- [x] Added a `users` table with normalized unique email, password hash, active flag, and one role per user.
- [x] Added registration, login, and current-user endpoints.
- [x] Added JWT authentication and reusable role authorization; contribution admin routes now require an admin role.
- [x] Prevented public registration from selecting privileged roles and added local administrator provisioning.
- [x] Added auth tests and verified migrations on fresh and copied legacy databases.
- [x] Expand `/api/health` to report database and Ollama status.
- [x] Add organization, incident, and location tables with migrations.
- [x] Add needs, raw reports, and the shared hash-linked audit log.
- [x] Complete the Phase 0.4 report parser, idempotent report intake, filtered needs endpoint, and audit logging.
- [ ] Complete the Phase 0.5 coordinator situation snapshot and draft proposal workflow.

### Module 1: Skilled Volunteer Coordination

**Status:** Complete for the Module 1 backend scope.

Implemented: controlled skills and seed command, volunteer profiles and verification, organization-scoped administration, availability windows, estimated routing and blockage recomputation, code-validated matching, human-approved assignment lifecycle, coverage, opt-in reassignment suggestions, and schema-validated AI skill mapping/explanations with call logging and rule fallbacks. Match scores expose verified skill level, route duration, current commitments, equipment, language, and organization trust. AI can only describe code-ranked candidates and cannot change scores or assignments. The mobile form still stores text locations locally; matching requires a location with coordinates.

### Module 2: Disaster Intelligence and Feedback

**Status:** Complete for the Module 2 backend scope.

Implemented: CSV/GeoJSON baseline and historical imports, incident-scoped raw reports, estimated baseline/location profiles, verified damage assessments, resource stock and atomic reservations, idempotent allocations and confirmations, dispatched-vs-confirmed progress, Need remaining calculations, situation and recovery reports, repeatable on-demand and scheduled bottleneck scans, and optional AI duplicate judging/explanations/recovery narratives. Estimated, reported, verified, and confirmed data remain separate. Ollama is optional; detection and delivery operations work without it.

### Module 3: Offline SOS and Relay Sync

**Status:** Complete for backend intake, synchronization, and coordinator actions.

Implemented: unauthenticated save-first SOS intake, client-UUID idempotency, location honesty, near-duplicate links, API-key gateway auth, per-item batch sync, SMS compact/report parsing, sender/gateway/IP rate limits, coordinator polling/ack/dispatch/resolve, assignment linkage, audit logs, and background AI interpretation with schema validation and rule fallback. Hardware relays remain gateway-side.

## 4. Day-by-Day Work Plan

| Day | Work item | Status |
|---|---|---|
| Day 1 | Review the existing backend, contribution ledger, database, and requirements. | Complete |
| Day 2 | Add environment-backed database configuration and Alembic migration foundations. | Complete |
| Day 3 | Add database/Ollama health diagnostics and complete setup verification. | Complete |
| Day 4 | Define the user model, password hashing, and supported roles. | Complete |
| Day 5 | Implement registration, login, JWT issuance, and current-user retrieval. | Complete |
| Day 6 | Add reusable role authorization, admin bootstrap, auth migration, and tests. | Complete |
| Day 7 | Add organization, incident, and location models with migrations. | Complete |
| Day 8 | Add needs and raw reports with verification and confidence fields. | Complete |
| Day 9 | Extend the hash-linked ledger into the shared audit-log service. | Complete |
| Day 10 | Add core schemas, seed skeleton, and shared-record tests. | Complete |
| Day 11 | Build the Ollama client with JSON validation, timeout, retry, and call logging. | Complete |
| Day 12 | Define the report parser schema and versioned prompt. | Complete |
| Day 13 | Add the rule-based parser fallback and evaluation cases. | Complete: deterministic cases cover family counts and multiple needs. |
| Day 14 | Implement report intake and needs endpoints; verify the report-to-needs milestone. | Complete |
| Day 15 | Build the coordinator situation snapshot and proposal model. | Remaining |
| Day 16 | Add a validated, draft-only coordinator tool registry. | Remaining |
| Day 17 | Implement proposal review, approval/rejection, AI status, and coordination tests. | Remaining |
| Day 18 | Add controlled skills and volunteer profile models. | Complete |
| Day 19 | Add skill verification, volunteer availability, and availability windows. | Complete |
| Day 20 | Implement Haversine estimates, the RoutingClient interface, and road blockages. | Complete |
| Day 21 | Build code-validated matching candidates and ranked score breakdowns. | Complete |
| Day 22 | Add assignment proposals, coordinator approval, and lifecycle tests. | Complete |
| Day 23 | Add coverage, surplus detection, reassignment suggestions, and Module 1 milestone checks. | Complete |
| Day 24 | Add baseline, historical incident, and hazard-zone import foundations. | Complete |
| Day 25 | Add resource stock and transactional allocation to prevent double reservation. | Complete |
| Day 26 | Add movement tracking, delivery confirmations, and remaining-need calculations. | Complete |
| Day 27 | Add bottleneck scans, situation summaries, recovery reports, and Module 2 milestone checks. | Complete |
| Day 28 | Add idempotent SOS intake, compact parsing, and location honesty rules. | Complete |
| Day 29 | Add gateway authentication, batch sync, near-duplicate flags, and SMS/mesh simulation. | Complete |
| Day 30 | Add SOS acknowledgements and dispatch links, background interpretation, permissions checks, and an end-to-end demo. | Complete: endpoint flows and mocked AI fallbacks tested. |

## 5. Remaining Work

1. Complete the Phase 0.5 coordinator situation snapshot and draft-only proposal workflow.
2. Add cross-module demo seed data, broader AI evaluation cases, and full end-to-end workflow verification.

## 6. Authentication and Verification

From the `backend` directory in PowerShell:

```powershell
Copy-Item .env.example .env
# Set JWT_SECRET in .env to a random value of at least 32 characters.
.\.venv\Scripts\Activate.ps1
alembic upgrade head
python -m app.bootstrap_admin admin@example.org
python -m pytest -q
```

The authentication milestone is complete when registration creates a community account, login returns a bearer token, `/auth/me` reports the authenticated profile, and admin-only routes reject non-admin roles. Public registration cannot select a role.
