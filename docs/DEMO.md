# Four-Minute Demo and Presentation

The demo should make one point clear: a messy request becomes a reviewable
response, and the ledger tracks what actually arrived. Show the AI source
label as well as the proposal. A fallback demonstration is useful resilience
evidence, but it is not evidence that the model made the decision.

## Before Recording

Follow [SETUP.md](SETUP.md). Open the public app at
http://127.0.0.1:52394 and the Service Station at
http://127.0.0.1:52396. Confirm the backend at
http://127.0.0.1:8000/api/health and keep its API explorer available at
http://127.0.0.1:8000/docs for operations without a visible UI control.

Use a disposable demo database, not real requests. Sign in with the documented
local demo accounts. Prepare an incident/location, a need with verified skilled
volunteers and availability, and stock sufficient for a partial-delivery example.
Use returned record IDs, not assumed seed IDs.

Rehearse the actual model call first. The saved evaluation's five live cases
all timed out into fallback. Do not silently replace a failed live call with
a mocked response or prerecorded result. If showing an earlier successful
result, identify when it was recorded and show its provenance.

## Recording Script

| Time | Show | Say |
|---|---|---|
| 0:00-0:20 | Public app and coordinator station | "Requests, volunteer availability and supply deliveries often sit in different places. Rahat puts them into one response workflow, even when the sender needs to retry." |
| 0:20-0:55 | Submit a report such as `School ma 40 families chan, khane pani chaina, elderly lai medicine chahiyo.` Supply a known incident/location if needed. Show parsed needs, missing fields and source | "The parser turns the message into structured fields. The backend consumes those fields to create unverified needs. It stores follow-up questions; it does not automatically chat with the reporter." |
| 0:55-1:15 | A location profile and `/api/exposure` evidence | "Baseline households are estimates. Requests are reported, and field confirmations are separate. These demo records are synthetic unless a source and date are shown." |
| 1:15-1:45 | Parse a pasted road notice, inspect the pending record, verify a rehearsed coordinate/radius and recompute the same route | "AI extracts the notice. A coordinator verifies its location before it affects a route. This is a geometric estimate, not road-network navigation." |
| 1:45-2:25 | Run `POST /ai/coordinate?incident_id=...` with a new client UUID. Show assignment/allocation drafts, rationale, confidence and source | "Code checks feasible candidates and stock. The model can select only supplied options. These are drafts, not autonomous dispatches; confidence does not bypass approval." |
| 2:25-3:00 | Approve one draft. For supplies, confirm a partial receipt, for example 40 of 100 requested units | "Approval and volunteer acceptance are separate. Sending 100 units does not fulfill a need. Confirming 40 received leaves 60 outstanding." |
| 3:00-3:30 | Queue a synthetic SOS while offline, reconnect and retry. Repeat the same batch/request UUID | "The sender retains the original ID, so a repeated upload does not create another SOS. A receipt means the server saved it, not that help arrived." |
| 3:30-4:00 | Root AI disclosure and the evaluation table | "The keyword baseline scored 66.67% on 30 synthetic messages. The five live-model attempts all used fallback after timeouts, so we do not yet have AI-only accuracy or a proven quality improvement." |

Model calls can exceed the time allocated in this outline. The four-minute
target is a recording plan, not an inference-time guarantee. Use a clearly
labelled recorded segment if necessary; keep failures and source labels honest.

## Rehearsal Details

- The relevant API operations are `POST /reports`, `POST /road-updates`,
  `POST /road-updates/{report_id}/verify`, `POST /routes/compute`,
  `POST /ai/coordinate`, and the assignment/allocation approval routes.
  Use the API explorer for current schemas and authorization.
- A skill mapper runs only when required skills are absent. If the parser
  already supplied them, explain that branch rather than claiming a second
  AI call happened.
- Road verification alone does not guarantee a visible detour. Rehearse a
  synthetic blockage intersecting the chosen estimated path; label it a demo
  fixture rather than an actual closure. Otherwise show the unchanged result.
- Without verified census, BIPAD or DHM imports, do not describe the location
  screen as a live government feed. See [DATA_SOURCES.md](DATA_SOURCES.md).
- Use browser offline mode, then restore connectivity and retry the saved
  SOS. Do not change its UUID or server address. For batch replay, reuse the
  same request payload and check the returned identifiers/counts.
- Mesh Lab is a labelled simulation. It is not proof of Bluetooth or LoRa
  transport. Do not call real emergency numbers during a demo.
- Hide personal messages, coordinates, tokens and private configuration in
  the recording. Use synthetic records and local demonstration accounts.

## Six-Slide Alternative

1. **Problem:** fragmented requests, uncertain response status and supply gaps.
2. **Workflow:** intake, structured needs, feasible options, review, field evidence.
3. **Architecture:** two Flutter clients, one backend/database, local Ollama.
4. **AI contribution:** exact producer/consumer functions and the human approval boundary.
5. **Evidence:** partial receipt math, UUID replay, measured evaluation and timeouts.
6. **Limits and next steps:** better inference reliability, richer context,
   audited data imports and outcome evaluation; no autonomous-dispatch claim.

This file is a recording/presentation script, not a completed video. Before
submission, record the demonstrated build and add the actual video or slide
URL to [CHECKLIST.md](CHECKLIST.md).
