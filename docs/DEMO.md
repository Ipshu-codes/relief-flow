# Demo runbook and presentation outline

## Prepare

Follow [setup](README.md), seed with `--demo`, build Flutter and start the backend.
Use localhost only for public demo accounts. Keep Ollama/model loaded; allow
for slower CPU inference. If it times out, show the explicit fallback label.

## Reliable demonstration (4-6 minutes)

1. Open http://127.0.0.1:8000/. Show the original dark palette and large
   **Request emergency help** action. Select Medical or Trapped, supply a manual
   location near the demo health post, optionally add a note, and send.
   Show **Received by server**; this is not a help-arrival promise.
2. Open Response and sign in as `coordinator@demo.rahat.org` using the documented
   local demo password. Open **SOS Queue**. Refresh if necessary (automatic
   refresh is 15 seconds), acknowledge the event, then inspect the resulting need.
3. Review/verify an appropriate need. On the seeded solar-repair need, choose
   **Match Volunteers** for score breakdowns, then **AI Draft** for a model-selected
   candidate and rationale. Show `source=ai` or honestly `fallback`. The seeded
   technician has a verified skill and availability window.
4. Approve the proposed assignment. Sign in as the demo volunteer and move
   through accept, en-route, on-site, completion with outcome. Explain that a
   draft is not dispatch and a supply need cannot complete from a task outcome.
5. On the seeded water need, allocate stock, dispatch/deliver, then confirm a
   partial receipt. Show **remaining = requested - confirmed**, not sent.
   Run a bottleneck scan and inspect evidence.
6. Volunteer registration: create a community account, then Create My Profile,
   add multiple skills and an availability window. Skills initially unverified.
   For employer flow create another community account, Register my organization,
   register an employee with multiple skills/contact details, then verify skills
   from an authorized manager account.
7. Coordinator **Mesh Lab**: check bridge (initially disconnected), send a test
   SOS (queued, not received), toggle bridge, then see it in SOS Queue.
   Explain synthetic coordinates and that physical Bluetooth is not claimed.
8. Show [AI evaluation](AI_EVALUATION.md) and [AI disclosure](AI_USAGE.md).
   Do not present mock unit tests as live-model accuracy.

## Offline retry demonstration

On a separate local browser app, use the browser's offline network mode,
send an SOS, show **Saved on device / not received**, restore connectivity,
then choose **Retry saved SOS**. The original client UUID is reused.
Do not change the server address to simulate offline: that would send a real
request to a different server, not test the same delivery path.

## Six-slide presentation / recording script

1. **Problem (25s):** fragmented requests, unverified volunteers, supply
   dispatches mistaken for delivery.
2. **Solution (35s):** one shared receiver and role-aware workspace; resilient
   SOS storage and traceable decisions.
3. **Intake (45s):** public SOS, honest GPS, durable retry, command acknowledgement.
4. **AI with guardrails (60s):** messy report -> validated needs -> feasible
   candidates -> model choice -> human approval. Show real provenance.
5. **Feedback (45s):** volunteer outcome and partial stock receipt change actual
   persisted status; evidence exposes shortages.
6. **Value and limits (30s):** local open-weight AI, offline resilience and
   accountable coordination. Explicitly state estimated routes and simulated radio.

A video is not automatically recorded by this task. This file is the ready-to-use
presentation/recording outline; record the demonstrated steps rather than
claiming unavailable live feeds or physical mesh capabilities.
