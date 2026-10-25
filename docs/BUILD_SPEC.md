# Rahat: Backend and AI Build Spec

*Hand this document to your AI coding assistant at the start of every session. It describes what to build, in what order, and the rules to follow.*

## 1. What we are building

Rahat is an AI-assisted disaster response backend (REST API) with three modules, built in this order:

1. **Module 1: Skilled Volunteer Coordination.** Register verified volunteers, match them to needs, detect over- and under-staffing, suggest reassignments, and re-route around blocked roads.
2. **Module 2: Disaster Intelligence and Feedback.** Hold pre-disaster baseline data, combine live reports, track requested vs delivered resources, and detect bottlenecks, duplicates and unresolved needs.
3. **Module 3: Offline SOS and Relay Sync.** Accept SOS messages that were created offline or relayed through a gateway, de-duplicate them, and sync them into the central database.

The frontend (Flutter app and Leaflet web map) will call this API later. For now, the goal is a **working, tested backend plus an AI layer**, usable through Swagger docs at `/docs`.

## 2. Golden rules (the AI assistant must follow these)

1. **Code decides, AI explains.** Matching eligibility, distances, routes, inventory math, status changes and permissions are always done by ordinary code. The language model only does three things: read messy text into structured data, rank or choose among options the code already validated, and write human-readable explanations.
2. **The LLM never invents facts.** It must not invent roads, coordinates, volunteer skills, quantities or statuses. Every LLM output is validated against a Pydantic schema before it touches the database. If validation fails, retry once, then fall back to a rule-based result.
3. **Everything works without AI.** If Ollama is down, SOS intake, volunteer registration, assignments and delivery tracking must still work. AI endpoints return a rule-based fallback marked `"source": "fallback"`.
4. **Important actions stay drafts until a human approves.** AI can create a *proposed* assignment or reassignment. A coordinator approves it before it becomes active.
5. **A need is closed only by completion criteria, never by "dispatched".** For supplies: `remaining = requested - confirmed_received`. For tasks: the field team records an outcome and the criteria are met.
6. **Estimated is not verified.** Baseline household counts are estimates. Reports are unverified until a coordinator or trusted user verifies them. Always store and return a `verification_status` and a `confidence` label.
7. **Idempotent writes.** Any endpoint that offline clients or gateways may retry accepts a client-generated `client_uuid` and must never create duplicates.
8. **Every state change is logged** in the audit log (hash-linked, reusing the existing ledger idea).
9. **Small steps.** Build one module slice at a time, with tests, and keep the app runnable after every step.

## 3. Tech stack

| Layer | Choice |
| --- | --- |
| API | Python 3.11+, FastAPI, Pydantic v2, Uvicorn |
| Database | PostgreSQL with PostGIS (run with Docker Compose). SQLAlchemy 2 plus GeoAlchemy2 |
| Migrations | Alembic (replace the current `create_all`) |
| Auth | JWT bearer tokens, role-based (see section 5) |
| AI | Ollama (local), Python `ollama` client. Start with a small instruct model such as Qwen3 or Llama 3.1 8B. Optional cloud provider behind the same interface |
| Routing | OSRM or Valhalla running locally on a regional OpenStreetMap extract (Nepal region or a single district) |
| Optimization | Google OR-Tools for assignment and reassignment |
| Geo math | Haversine for straight-line distance, PostGIS for spatial queries |
| Background jobs | Simple: FastAPI background tasks or APScheduler. No Celery for the MVP |
| Tests | pytest, httpx test client, a test database |

### What exists already (from the earlier prototype)

- FastAPI app, health route, CORS, SQLite plus SQLAlchemy.
- A SHA-256 hash-linked ledger for verified contributions. **Reuse this as the audit log.**
- Admin token auth. **Replace with role-based JWT.**
- Empty `ai/` and `pipelines/` folders. **The AI layer lives here.**
- Contributions and verification. Optional: keep as a "donations" feature later; it is not part of the three core modules.

## 4. Repository structure

```
backend/
  app/
    main.py
    core/            # config, security, db session, logging, errors
    models/          # SQLAlchemy models, one file per area
    schemas/         # Pydantic request, response and AI-output schemas
    api/
      v1/            # routers: auth, volunteers, needs, assignments, ...
    services/        # business logic (matching, routing, tracking, sync)
    ai/
      client.py      # Ollama wrapper with timeout, retry, JSON mode
      prompts/       # prompt templates as files
      parsers.py     # report parser
      explainers.py  # explanation writers
      fallbacks.py   # rule-based replacements
    geo/             # haversine, routing client, PostGIS helpers
    ledger/          # hash-linked audit log
    seed/            # demo data scripts
  alembic/
  tests/
  docker-compose.yml  # postgres+postgis, ollama (optional), osrm (optional)
  .env.example
  README.md
```

## 5. Phase 0: shared foundation (build this first)

Nothing in the three modules works without this. Finish it completely before starting Module 1.

**0.1 Project setup**

- Docker Compose with PostgreSQL plus PostGIS. `.env.example` with `DATABASE_URL`, `JWT_SECRET`, `OLLAMA_URL`, `OLLAMA_MODEL`, `OSRM_URL`.
- Alembic configured. A single `make dev` or README section that gets the API running from scratch.
- Health route that also reports DB status and whether Ollama is reachable.

**0.2 Auth and roles**

- Roles: `community_member`, `volunteer`, `org_admin` (NGO or hospital representative), `coordinator`, `admin`.
- Routes: `POST /auth/register`, `POST /auth/login`, `GET /auth/me`.
- A reusable dependency such as `require_role(...)` for protecting routes.
- SOS submission (Module 3) must also work for **unauthenticated** or device-token users, because people in distress cannot be forced to log in.

**0.3 Core tables used by all modules**

- `users`, `organizations`.
- `locations`: settlements, wards, shelters, health posts (name, type, PostGIS point, optional boundary, parent location, baseline households estimate).
- `incidents`: one disaster event (type, start time, status, affected area).
- `needs`: the central table. Fields: id, incident\_id, location\_id, category (`rescue`, `medical`, `water`, `food`, `shelter`, `technical_repair`, `other`), description, required\_skills (list), quantity\_requested, unit, quantity\_fulfilled, urgency (1 to 5), vulnerable\_groups, status (`open`, `partially_fulfilled`, `in_progress`, `fulfilled`, `closed`), verification\_status (`unverified`, `verified`, `rejected`), source (`sos`, `report`, `volunteer`, `coordinator`), source\_report\_id, last\_updated\_at.
- `raw_reports`: raw text, channel (`app`, `sms`, `mesh`, `web`), sender reference, client\_uuid (unique), received\_at, parse\_status, parsed\_json.
- `audit_log`: hash-linked entries (actor, action, entity, entity\_id, before, after, timestamp, prev\_hash, hash).

**0.4 AI foundation**

- `ai/client.py`: one function `generate_json(prompt, schema, ...)` that calls Ollama in JSON mode, enforces a timeout, validates with Pydantic, retries once, and raises a typed error on failure.
- `ParsedReport` schema:

  ```
  ParsedReport {
    location_text, families_affected (int or null),
    needs: [{category, item, quantity, unit, required_skills[]}],
    urgency (1-5), vulnerable_groups[], hazards[],
    missing_fields[], follow_up_questions[], language, confidence (low|medium|high)
  }
  ```
- `POST /reports` (raw text plus channel plus client\_uuid) stores the raw report, runs the parser, creates `needs` rows with `verification_status=unverified`, and returns the parsed result. If AI fails, the report is stored with `parse_status=pending` and a rule-based keyword parse creates a minimal need.
- `GET /needs`, `GET /needs/{id}`, `PATCH /needs/{id}` (coordinator only), with filters by incident, location, category, status, urgency.

**Done when:** a message such as "40 families at the school, no drinking water, elderly need medicine" becomes two or more `needs` rows, visible in `GET /needs`, and the action appears in the audit log.

## 6. Module 1: Skilled Volunteer Coordination

### 6.1 Goal

Register verified skilled volunteers, find qualified and available people for a need, propose assignments, detect surplus and shortage, and re-route when roads or availability change.

### 6.2 Tables

- `volunteer_profiles`: user\_id, organization\_id, home or base location (PostGIS point), max\_travel\_km, availability\_status (`available`, `assigned`, `unavailable`, `off_duty`), languages, equipment (list), notes.
- `skills`: a controlled vocabulary (name, category), for example `solar_technician`, `electrician`, `doctor`, `nurse`, `civil_engineer`, `boat_rescue`, `first_aid`, `water_purification`.
- `volunteer_skills`: volunteer\_id, skill\_id, level, certification\_name, certificate\_ref, **verified (bool), verified\_by, verified\_at**.
- `availability_windows`: volunteer\_id, start, end.
- `assignments`: id, need\_id, volunteer\_id (or team\_id), status (`proposed`, `approved`, `accepted`, `en_route`, `on_site`, `completed`, `cancelled`, `rejected`), proposed\_by (`ai`, `coordinator`), route\_id, eta, approved\_by, outcome\_notes, completion\_criteria\_met (bool), timestamps.
- `routes`: id, from\_point, to\_point, geometry (LineString), distance\_km, duration\_min, blocked\_segments\_considered, computed\_at, engine.
- `road_blockages`: id, location or segment (geometry), reported\_by, verified, reported\_at, cleared\_at, notes.

### 6.3 Endpoints

- `POST /volunteers` and `GET /volunteers` (filters: skill, area, availability, verified only).
- `PATCH /volunteers/{id}`, `POST /volunteers/{id}/skills`, `POST /volunteers/{id}/skills/{skill_id}/verify` (org\_admin or coordinator).
- `PATCH /volunteers/{id}/availability`.
- `POST /needs/{need_id}/match` returns ranked candidate volunteers (see 6.4). Does not change any data.
- `POST /assignments` creates an assignment (usually `proposed`).
- `POST /assignments/{id}/approve`, `/accept`, `/reject`, `/status`, `/complete`.
- `POST /blockages`, `PATCH /blockages/{id}/clear`.
- `POST /routes/compute` (from, to) returns route, ETA and whether it avoids known blockages.
- `GET /coverage?incident_id=` returns, per location, required vs assigned skills (shortage and surplus).
- `GET /reassignment-suggestions?incident_id=` (see 6.6).

### 6.4 Matching logic (code, not AI)

For a need, build the candidate list in this order:

1. **Hard filters:** volunteer holds a **verified** required skill, is `available`, has an availability window covering the task, is within `max_travel_km`, and a route exists.
2. **Score** each candidate with transparent weights: skill level, route duration (from the routing engine), whether the volunteer is already assigned elsewhere, equipment match, language match, and organization trust.
3. Return the top N with a score breakdown. Use OR-Tools when assigning many volunteers to many needs at once (minimize total travel time, respect skill and capacity constraints).

### 6.5 AI work in this module

- **Need to skills:** the report parser (Phase 0) outputs `required_skills`. Add a second helper that maps free text such as "health post has no electricity, fridge not working" to skill vocabulary terms (`solar_technician`, `electrician`) and equipment hints. Output must use only skills from the `skills` table.
- **Explanations:** `POST /needs/{id}/match?explain=true` asks the LLM to write a short reason for the top candidates, given the score breakdown. The LLM cannot change the order.
- **Trade-off summaries** for reassignment proposals (see 6.6).

### 6.6 Reassignment and re-routing

- **Surplus detection:** a location has more verified, available responders of a skill than its open needs require (with a safety buffer).
- **Suggestion:** find an underserved location needing that skill. Before suggesting, the code checks travel time, remaining coverage at the source location, and the volunteer's willingness and range. Output a `proposed` assignment plus a trade-off explanation.
- **Approval:** reassignments are never automatic. A coordinator must approve.
- **Blockage event:** when a blockage is created or verified, find active routes that intersect it, recompute with the segment excluded, and either update the ETA or create a notification suggesting an alternative volunteer or path.
- **Volunteer becomes unavailable:** reopen the need, rank replacements, and notify the coordinator.

### 6.7 Done when

- A solar-technician need at a health post returns a ranked list of verified, available technicians with route times.
- A surplus in one village produces a proposed reassignment with a clear explanation.
- Creating a blockage changes the route result.
- An assignment moves from `proposed` to `completed`, and the need closes only if completion criteria are met.

## 7. Module 2: Disaster Intelligence and Feedback

### 7.1 Goal

Build the picture before, during and after the disaster. Track requested vs delivered resources. Detect bottlenecks, duplicates and unresolved needs.

### 7.2 Tables

- `baseline_settlements`: location\_id, estimated\_households, estimated\_population, source (`OSM`, `census`, `manual`), data\_date, confidence.
- `baseline_features`: buildings, bridges, roads, health posts, shelters (type, geometry, source, imported\_at).
- `historical_incidents`: type, date, location or area, damage summary, source (for example BIPAD export).
- `hazard_zones`: area geometry, hazard type (`flood`, `landslide`), risk level.
- `resources`: type (water, food, medicine, equipment), unit, description.
- `resource_stock`: organization\_id, resource\_id, quantity\_available, quantity\_reserved, location.
- `resource_requests` (links to `needs`) and `resource_movements`: need\_id, resource\_id, quantity, status (`allocated`, `dispatched`, `delivered`, `confirmed`), dispatched\_at, delivered\_at, confirmed\_by, quantity\_confirmed.
- `delivery_confirmations`: movement\_id, confirmed\_by, status (`full`, `partial`, `not_received`), quantity\_received, notes.
- `damage_assessments`: location\_id, kind (`pre`, `post`), verified, verified\_by, damage\_level, details, evidence\_ref, assessed\_at.
- `bottleneck_flags`: type, location\_id, need\_id, severity, evidence (JSON), status (`open`, `acknowledged`, `resolved`), detected\_at, explanation.

### 7.3 Endpoints

- `POST /admin/import/baseline` (GeoJSON or CSV upload of settlements and features), `POST /admin/import/historical`.
- `GET /locations/{id}/profile` returns baseline, hazards, current needs, verified damage, assistance delivered.
- Resources: `POST /resources/stock`, `GET /resources/stock`, `POST /allocations` (reserve stock for a need, with no double allocation), `PATCH /movements/{id}/status`.
- `POST /movements/{id}/confirm` (community or volunteer confirms full, partial or not received). Recalculates the need, flags dispatched vs received mismatch, writes to the audit log.
- `GET /needs/{id}/progress` returns requested, allocated, dispatched, delivered, confirmed and remaining.
- `GET /situation?incident_id=` returns summary counts and per-location status for the dashboard and map.
- `GET /bottlenecks?incident_id=` and `PATCH /bottlenecks/{id}`.
- `POST /bottlenecks/scan` runs detection now; a scheduled job also runs it periodically.
- `GET /reports/recovery?incident_id=` generates a post-disaster summary (before/after, assistance delivered, outstanding gaps).

### 7.4 Core rules (code)

- `remaining = quantity_requested - quantity_confirmed`. A need becomes `fulfilled` only when remaining is 0 after confirmation.
- Stock reservation uses a transaction with row locking so the same stock cannot be reserved twice.
- A movement marked `delivered` by a provider but not confirmed by the community stays "unconfirmed" and appears in the bottleneck scan after a time limit.
- Keep three separate concepts in every response: **estimated exposure** (baseline), **reported need**, **verified damage**.

### 7.5 Bottleneck detection

Deterministic checks run first (SQL and Python):

- **Silent areas:** settlement in a hazard zone with few or no reports, relative to its baseline.
- **Stalled deliveries:** movement `dispatched` longer than X hours with no confirmation.
- **Partial or missing deliveries:** confirmation shows less than dispatched.
- **Unstaffed needs:** open need with required skills and no accepted assignment after X hours.
- **Duplicate assignments:** same need or the same volunteer double-booked in overlapping windows.
- **Blocked access:** open needs whose only known route crosses a verified blockage.
- **Stale reports:** no update within the freshness window.

AI is then used only for ambiguous cases:

- **Duplicate report clustering:** group reports with similar location and text (use a text similarity measure first; ask the LLM to judge only borderline pairs, and return a confidence).
- **Explanations:** one short paragraph per flag, written from the evidence JSON.
- **Recommended next actions** as suggestions, never automatic changes.

### 7.6 Feedback loop

Store verified confirmations and community feedback. Use them to adjust the priority score (for example, locations with repeated unconfirmed or partial deliveries rise in priority) and to produce a lessons-learned section in the recovery report. Start with simple counters and rules; no model training in the MVP.

### 7.7 Satellite and external data

Treat these as **offline imports**, not live dependencies. For the prototype, prepare one region in advance: OpenStreetMap extract (roads, buildings, health posts), a BIPAD export if accessible, and optionally one pre-downloaded Copernicus flood-extent file. Import it through the admin import routes. Do not build live satellite analysis in the first version.

### 7.8 Done when

- Importing a settlement file shows a baseline in `GET /locations/{id}/profile`.
- A partial delivery leaves the correct remaining quantity and creates a mismatch flag.
- `POST /bottlenecks/scan` flags a stalled delivery, an unstaffed need and a silent hazard-zone settlement in the demo data, each with an explanation.

## 8. Module 3: Offline SOS and Relay Sync

### 8.1 Goal

The backend is the **receiving end**. The Flutter app stores SOS messages offline and relays through Meshtastic or peer devices. The backend must accept them whenever they arrive: late, repeated, out of order, or in a compact format.

### 8.2 Tables

- `sos_events`: id, client\_uuid (unique), sender\_ref (user, device or phone), lat, lon, location\_accuracy\_m, category (`FOOD`, `MEDICINE`, `TRAPPED`, `RESCUE`, `OTHER`), message (short), created\_at\_device, received\_at\_server, channel (`app`, `mesh`, `sms`, `gateway`), relay\_path (list of hops), transmission\_status, status (`new`, `acknowledged`, `dispatched`, `resolved`, `false_alarm`), linked\_need\_id, duplicate\_of, has\_location (bool).
- `gateways`: id, name, type (`meshtastic`, `sms`, `app`), api\_key\_hash, last\_seen\_at.
- `sync_batches`: id, gateway\_id, received\_at, count\_received, count\_new, count\_duplicate (for debugging and audit).
- `sos_acknowledgements`: sos\_id, by\_user, action, timestamp.

### 8.3 Endpoints

- `POST /sos` (single SOS from a connected app). Accepts a compact payload: client\_uuid, lat, lon, category, message, created\_at\_device.
- `POST /sync/sos-batch` (from a gateway or an app that was offline). Accepts a list; returns per-item result (`created`, `duplicate`, `rejected`) so the sender knows what to drop from its queue. **Must be idempotent on client\_uuid.**
- `POST /gateways` (admin) and gateway authentication with an API key header.
- `GET /sos?status=&since=` for coordinators, with distance from a given point (Haversine) and age.
- `POST /sos/{id}/ack`, `/dispatch` (creates or links an assignment from Module 1), `/resolve`.
- `GET /sos/{id}` returns the incident, timestamps, relay path and transmission status.
- `POST /sms/incoming` webhook: maps phone number plus text to a `raw_report` (channel `sms`) or an `sos_event`, depending on format. For the MVP, also provide a **simulator** route or script that fakes SMS and mesh messages.
- `GET /sos/stream` (Server-Sent Events) or simple polling endpoint for the live coordinator map.

### 8.4 Rules

- **No AI in the critical path.** An SOS is saved first, instantly. Anything AI does happens afterwards, in the background.
- **Dedupe:** exact duplicates by `client_uuid`; near duplicates (same sender within a small time window and radius) are flagged with `duplicate_of`, not deleted.
- **Location honesty:** if lat/lon are missing or zero, set `has_location=false`. Do not guess coordinates.
- **Compact format:** support a short text format that fits a mesh message, for example `SOS|TRAPPED|27.7172,85.3240|water rising`, and parse it with plain code.
- **Time:** store both device time and server time. Use device time for ordering and server time for audit.
- **Spam control:** rate limit per sender and per gateway. Allow unauthenticated SOS, but mark `sender_verified=false`.

### 8.5 AI work in this module (background only)

- Interpret free-text SOS messages (including Romanized Nepali) to suggest a category and urgency if the user did not choose one.
- Link an SOS to an existing need, or create a need (`source=sos`, `unverified`) with `required_skills` filled in.
- Flag likely duplicates among nearby SOS events.
- Never delay, block or reject an SOS because AI failed.

### 8.6 Done when

- Sending the same SOS batch twice creates no duplicates and returns `duplicate` for the second pass.
- A compact mesh-style string becomes a valid `sos_event`.
- A coordinator can acknowledge, dispatch (linking an assignment) and resolve an SOS.
- With Ollama turned off, SOS intake still works end to end.

## 9. AI layer: full list of tasks

All AI code lives in `app/ai/`. Every task has: a Pydantic output schema, a prompt file, a rule-based fallback, and tests.

| ID | Task | Input | Output | Fallback |
| --- | --- | --- | --- | --- |
| AI-1 | Report parser | Raw message | `ParsedReport` | Keyword rules for water, food, medicine, rescue, shelter plus a number regex |
| AI-2 | Skill mapper | Need description | Skill names from the controlled list | Keyword to skill table |
| AI-3 | Match explainer | Score breakdown | Short reason per candidate | Template string from the scores |
| AI-4 | Reassignment explainer | Source and target coverage, travel time | Trade-off summary | Template string |
| AI-5 | Duplicate judge | Two reports | same or different, confidence | Distance plus text similarity threshold |
| AI-6 | Bottleneck explainer | Flag evidence JSON | One paragraph with a suggested action | Template per flag type |
| AI-7 | SOS interpreter | Free-text SOS | category, urgency, needs | Category chosen by user, default urgency 3 |
| AI-8 | Recovery report writer | Aggregated stats | Narrative summary with confidence labels | Table-only report |

**Implementation notes**

- Use JSON mode and low temperature (0 to 0.2) for parsing tasks.
- Keep prompts in `prompts/*.txt` with a version number. Log prompt version, model name and latency with each AI call.
- Add a `GET /ai/status` route that reports which model is loaded and whether fallbacks are active.
- Support Romanized Nepali and English first. Proper Nepali script is future scope.
- Build an **eval set** of 25 to 30 messages (English, Romanized Nepali, messy, incomplete) in `tests/ai_eval/`, with expected outputs, and a script that prints parser accuracy. Re-run it whenever the prompt or model changes.
- Offline operation: Ollama runs on a field laptop with the model pre-downloaded. An online provider can sit behind the same `generate_json` interface. The Android on-device model question is out of scope for the backend.

## 10. Cross-cutting requirements

- **Pagination, filtering and consistent error format** on all list routes.
- **Idempotency:** `client_uuid` on every offline-created record (reports, SOS, confirmations).
- **Timestamps:** store everything in UTC.
- **Permissions matrix:** write it down once (who can verify skills, approve assignments, verify needs, confirm deliveries, manage gateways) and test it.
- **Seed data:** a script that creates one demo incident, 4 or 5 settlements with baselines, 15 volunteers with varied skills, stock from 3 organizations, a few needs, a blockage and some SOS events. Every module's "done" check should be demonstrable from this data.
- **Tests:** at least one happy-path test and one failure test per endpoint group, plus unit tests for matching scores, remaining-need math, stock reservation, SOS dedupe and the compact SOS parser.
- **README:** setup, environment variables, how to run Ollama and OSRM, how to seed data, how to run tests.

## 11. Build order and step-by-step prompts for the AI assistant

Work in this order. Finish and test each step before the next. After each step, update the README.

1. **Phase 0.1 and 0.2:** Docker, Postgres/PostGIS, Alembic, config, auth, roles.
2. **Phase 0.3:** core tables, audit log, seed script (skeleton).
3. **Phase 0.4:** AI client, `ParsedReport`, `POST /reports`, `GET /needs`. *Milestone: message to needs.*
4. **Module 1 (a):** skills, volunteers, verification, availability.
5. **Module 1 (b):** routing client (OSRM or Valhalla), blockages, `/routes/compute`.
6. **Module 1 (c):** matching, assignments and status flow, explanations. *Milestone: ranked, approved assignment.*
7. **Module 1 (d):** coverage, reassignment suggestions, blockage-triggered re-routing.
8. **Module 2 (a):** baseline import, location profiles, stock and allocations.
9. **Module 2 (b):** movements, confirmations, remaining-need logic, progress endpoint. *Milestone: partial delivery gives the right remainder.*
10. **Module 2 (c):** bottleneck scan, duplicate clustering, explanations, recovery report.
11. **Module 3 (a):** SOS tables, `POST /sos`, compact parser, gateways and authentication.
12. **Module 3 (b):** batch sync with idempotency, dedupe, SMS and mesh simulator.
13. **Module 3 (c):** coordinator actions (ack, dispatch, resolve), live feed, background AI linking.
14. **Hardening:** eval accuracy numbers, permissions tests, full demo run from seed data.

**A reusable prompt to give your AI assistant for each step:**

> You are building the Rahat backend. Read the Rahat Backend and AI Build Spec. We are now on step N: \[name\]. Follow the golden rules: code decides and AI explains, everything works without AI, important actions stay drafts until approved, all writes are idempotent and audit-logged. First list the files you will create or change, then implement, then write tests, then show me how to run and verify it with curl or Swagger. Do not start the next step.

## 12. Out of scope for the first version

- Live satellite analysis, automatic damage detection from imagery.
- Real LoRa hardware integration inside the backend (the backend only receives relayed messages through the gateway API).
- On-device mobile AI.
- Proper Nepali-script understanding.
- Payments, donation processing and public fundraising.
- Fully autonomous AI decisions. Humans approve all assignments and reassignments.

## 13. Cut order if time runs short

Cut in this order: recovery report and satellite imports, then duplicate clustering by AI, then SSE live feed (use polling), then OR-Tools optimization (use simple greedy matching), then Valhalla (keep OSRM only). **Never cut:** audit log, remaining-need logic with confirmations, idempotent SOS sync, and human approval for assignments.
