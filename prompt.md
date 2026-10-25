You are my senior backend + AI engineer on "Rahat", an AI-powered disaster
response coordination REST API. We build BACKEND AND AI ONLY (no frontend) for
now. If docs/SPEC.md exists, read it; where it conflicts with this prompt, this
prompt wins.



=====================================================
1. WHAT RAHAT IS
=====================================================
Rahat coordinates disaster response in Nepal. Three modules, built in order:
  M1. Skilled Volunteer Coordination: register verified skilled volunteers,
      match them to needs, detect surplus/shortage, propose reassignments,
      re-route around blocked roads.
  M2. Disaster Intelligence & Feedback: pre-disaster baseline data, live
      reports, requested vs delivered tracking, bottleneck/duplicate/
      unresolved-need detection, recovery reports.
  M3. Offline SOS & Relay Sync: accept SOS messages created offline or relayed
      by gateways (SMS/mesh), idempotent, deduplicated, synced into the
      central database.

=====================================================
2. AI IS THE CORE: THE "RAHAT COORDINATOR" AGENT
=====================================================
AI is not an add-on. It is the coordination brain that every workflow passes
through. Build one central AI Coordinator (app/ai/coordinator.py) that:

  UNDERSTANDS  messy, incomplete, mixed English/Romanized-Nepali messages and
               turns them into structured needs (location, people, category,
               urgency, vulnerable groups, required skills, missing info,
               follow-up questions).
  ASSESSES     looks at the whole situation (open needs, assignments, stock,
               blockages, delivery confirmations, report age) and ranks what
               matters most, with reasons.
  DECIDES      among valid options: picks and justifies the best volunteer,
               reassignment, or supply allocation from candidates that code has
               already verified as feasible.
  DETECTS      explains bottlenecks, ambiguous duplicates and unresolved needs.
  ACTS         through TOOLS. The agent calls registered tools such as
               create_need, propose_assignment, propose_reassignment,
               propose_allocation, flag_bottleneck, notify_coordinator,
               request_missing_info. Every tool only creates DRAFT/PROPOSED
               records or notifications. A human coordinator approves.
  REPORTS      writes situation summaries and recovery reports with
               confidence labels.

Implement the agent loop with Ollama tool-calling (or a JSON "action" schema if
the model handles tool-calling poorly): observe situation snapshot -> model
returns a validated plan/tool calls -> code validates each call against
business rules -> executes the safe draft action -> logs everything. Provide:
  - POST /ai/coordinate?incident_id=   runs one coordination cycle and returns
    what the AI observed, what it proposed, and why
  - GET  /ai/proposals                 pending AI proposals for human review
  - POST /ai/proposals/{id}/approve | reject
  - GET  /ai/status                    model name, reachable?, fallback active?
  - A scheduled coordination cycle (APScheduler) every N minutes, plus
    event-triggered cycles (new SOS, new blockage, delivery confirmed).
Every AI call logs: prompt version, model, latency, input summary, output,
validation result, and whether the fallback was used.

=====================================================
3. GUARDRAILS (never break)
=====================================================
1. AI proposes, code validates, humans approve. The LLM never directly changes
   quantities, stock, statuses, permissions, coordinates, or routes. Those are
   plain code. The LLM never invents roads, skills, quantities or locations:
   it may only choose among IDs/options supplied by code.
2. Every LLM output is validated with a Pydantic schema. On failure: retry
   once, then use the rule-based fallback and mark "source": "fallback".
3. The system works with Ollama OFF. SOS intake, registration, assignments and
   delivery tracking never depend on AI. SOS is saved first, instantly; AI
   runs afterwards in the background.
4. remaining_need = quantity_requested - quantity_confirmed_received. "Sent"
   or "dispatched" never closes a need. Tasks close only when completion
   criteria are met.
5. Keep estimated (baseline), reported, and verified data separate. Always
   expose verification_status and confidence.
6. All offline-created records use client_uuid and are idempotent.
7. Every state change and every AI proposal/decision goes to the hash-linked
   audit log.
8. Stock reservation uses a transaction so the same stock can't be reserved
   twice.

=====================================================
4. STACK AND MACHINE LIMITS (8 GB RAM, Windows)
=====================================================
Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2, SQLite, Alembic, pytest,
APScheduler, httpx. NO Docker, NO PostgreSQL/PostGIS, NO Celery, NO OSRM.
Ollama at http://localhost:11434, model qwen2.5:3b (configurable by env:
OLLAMA_URL, OLLAMA_MODEL). Give PowerShell commands, not bash.
Use SQLAlchemy only (no SQLite-specific SQL) so we can move to PostgreSQL later.
GEO: plain lat/lon float columns, Haversine in Python. Routing sits behind a
RoutingClient interface in app/geo/ with an estimate-based implementation
(Haversine x 1.4 road factor / average speed, blockage check by distance from
verified blockage points to the path; return "source": "estimate"). Later we
can swap in OSRM without touching business logic.
Because the model is small: keep prompts short, give it few options at a time,
use JSON-constrained output, temperature 0-0.2, and rely on code for
anything numeric.

=====================================================
5. DATA MODEL (core tables)
=====================================================
users, organizations, roles (community_member, volunteer, org_admin,
coordinator, admin); locations (settlements, wards, shelters, health posts,
baseline households estimate); incidents; raw_reports (text, channel
app|sms|mesh|web, client_uuid unique, parse_status, parsed_json); needs
(category, description, required_skills, quantity_requested, unit,
quantity_fulfilled, urgency 1-5, vulnerable_groups, status, verification_status,
source, last_updated_at); audit_log (hash-linked); ai_proposals (type, payload,
reasoning, source ai|fallback, status pending|approved|rejected, created_at,
decided_by); ai_call_log.
M1: volunteer_profiles, skills (controlled vocabulary), volunteer_skills
(verified flag), availability_windows, assignments (proposed -> approved ->
accepted -> en_route -> on_site -> completed|cancelled|rejected), routes,
road_blockages.
M2: baseline_settlements, historical_incidents, hazard_zones, resources,
resource_stock, resource_movements (allocated -> dispatched -> delivered ->
confirmed), delivery_confirmations (full|partial|not_received), damage_
assessments, bottleneck_flags.
M3: sos_events (client_uuid unique, lat/lon, has_location, category FOOD|
MEDICINE|TRAPPED|RESCUE|OTHER, message, channel, relay_path, status,
duplicate_of, linked_need_id), gateways, sync_batches, sos_acknowledgements.

=====================================================
6. AI TASKS (each has: Pydantic schema, prompt file with version, call via
   app/ai/client.py generate_json, rule-based fallback, tests)
=====================================================
AI-1 Report parser: raw text -> ParsedReport {location_text, families_affected,
     needs[{category,item,quantity,unit,required_skills[]}], urgency 1-5,
     vulnerable_groups[], hazards[], missing_fields[], follow_up_questions[],
     language, confidence}. Fallback: keyword rules + number regex.
AI-2 Skill mapper: need text -> skills from the controlled list only.
AI-3 Prioritizer: code computes a transparent score (urgency, vulnerable
     groups, report age, unmet quantity, silent-area flag); the AI writes the
     reason and flags what a human should look at first.
AI-4 Match chooser: code builds feasible, ranked candidates; the AI picks and
     explains among them (cannot add candidates or change scores).
AI-5 Reassignment advisor: code detects surplus/shortage and checks travel
     time and remaining coverage; the AI writes the trade-off and recommends.
AI-6 Supply allocator: code lists valid stock options (never exceeding stock);
     the AI chooses and explains.
AI-7 Bottleneck explainer + duplicate judge: code finds flags; the AI judges
     borderline duplicate pairs (with confidence) and writes one-paragraph
     explanations and suggested next actions.
AI-8 SOS interpreter (background only): free-text SOS -> category, urgency,
     linked or new need.
AI-9 Situation/recovery report writer with confidence labels.
Plus: tests/ai_eval/ with 25-30 messages (English, Romanized Nepali, messy,
incomplete) with expected outputs and a script that prints parser accuracy.

=====================================================
7. HOW WE WORK (strict)
=====================================================
- ONE step at a time. Before coding each step: inspect the existing code, list
  the files you will create/change, tables/migrations and endpoints, and ask
  me questions if anything is ambiguous.
- Then implement, write tests (one happy path + one failure case per endpoint
  group, unit tests for scoring/math/dedupe/AI fallbacks, AI tests with Ollama
  both working and mocked as failing), and run them.
- Finish with: how I verify it (PowerShell + curl or Swagger at /docs), what
  the "Done when" result should look like, README/.env.example/seed updates,
  and a suggested commit message.
- Keep the app runnable after every step. Keep code simple and readable. Do
  not add features that aren't listed. If you think this plan is wrong, tell
  me instead of silently changing it. Do NOT start the next step until I say so.

BUILD ORDER:
 0.1 Setup: config, .env.example, Alembic on SQLite, health route (DB + Ollama
     status), README.
 0.2 Auth: register/login/me, role dependencies. SOS and report intake can
     work with a device token or no login.
 0.3 Core tables, hash-linked audit log (reuse existing ledger), seed skeleton.
 0.4 AI foundation: app/ai/client.py generate_json (JSON mode, timeout, one
     retry, validation, logging), AI-1 parser, POST /reports, GET/PATCH /needs.
     MILESTONE: "40 families at the school, no drinking water, elderly need
     medicine" becomes need rows.
 0.5 AI Coordinator skeleton: situation snapshot builder, tool registry
     (draft-only tools), ai_proposals table, /ai/coordinate, /ai/proposals,
     approve/reject, /ai/status.
 M1a skills, volunteers, verification, availability.
 M1b RoutingClient (estimate), blockages, /routes/compute.
 M1c matching (code) + AI-4 chooser, assignments flow with human approval.
     MILESTONE: a need yields a ranked, explained, approvable assignment.
 M1d coverage, surplus detection, AI-5 reassignment proposals, blockage-
     triggered re-routing.
 M2a baseline import, location profiles, stock and allocations (no
     double-booking), AI-6.
 M2b movements, confirmations, remaining-need logic, progress endpoint.
     MILESTONE: a partial delivery leaves the correct remainder and a flag.
 M2c bottleneck scan, AI-7, AI-9 recovery report, feedback-loop priority
     adjustment (simple counters).
 M3a SOS tables, POST /sos, compact parser ("SOS|TRAPPED|27.7172,85.3240|
     water rising"), gateways + API key auth.
 M3b POST /sync/sos-batch (idempotent, per-item created|duplicate|rejected),
     near-duplicate flagging, SMS/mesh simulator, /sms/incoming.
 M3c coordinator actions (ack/dispatch linking an assignment/resolve), live
     feed (polling), background AI-8 linking.
 Final: AI eval accuracy numbers, permissions tests, full demo from seed data
     (1 incident, 4-5 settlements, ~15 volunteers, stock from 3 organizations,
     needs, a blockage, SOS events).

=====================================================
8. EXISTING CODE
=====================================================
backend/ currently has FastAPI, SQLite, SQLAlchemy models for contributions,
a SHA-256 hash-linked ledger, an ADMIN_TOKEN guard, CORS for localhost:3000,
and empty app/ai and app/pipelines packages. Keep SQLite. Reuse the ledger
idea for audit_log. Replace ADMIN_TOKEN with role-based JWT. Put the AI layer
in app/ai. Contributions are not part of the three core modules, so leave them
alone unless they get in the way.

START NOW: summarize the existing code, then list your plan for steps 0.1 and
0.2 only. Wait for my "go".