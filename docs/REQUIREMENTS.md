# Requirements

## Functional
**Mobile**
- FR-M1 One-tap SOS with category (medical, trapped, fire, flood, food/water, shelter, missing person, other)
- FR-M2 Capture GPS, with last-known fallback if no fix; optional free text (EN/NE)
- FR-M3 Local persistence of outbox, inbox, and relay cache
- FR-M4 BLE advertise/scan relay with TTL and dedupe
- FR-M5 Offline map with SOS markers and station location
- FR-M6 Volunteer profile (skills, vehicle, availability)
- FR-M7 Receive assignments and acks addressed to the user
- FR-M8 Delivery-state tracking per SOS

**Gateway**
- FR-G1 Ingest packets from mesh bridge / Wi-Fi / USB
- FR-G2 Verify signatures, deduplicate by `msg_id`
- FR-G3 AI pipeline: extract → classify → score → dedupe cluster
- FR-G4 Priority queue API and WebSocket stream
- FR-G5 Matching engine (volunteers ↔ incidents)
- FR-G6 Offline routing with blocked-edge support
- FR-G7 Bottleneck and underserved-area analysis
- FR-G8 Coordinator dashboard (web)
- FR-G9 MCP server
- FR-G10 Audit log of all AI and human decisions
- FR-G11 Dispatcher agent with tool-calling (allowlisted tools, max steps, timeouts)
- FR-G12 Tiered action policy; T2 actions need approval; the full agent trace is stored and viewable
- FR-G13 Incident memory carried across agent runs
- FR-G14 Shared tool registry for the agent and MCP
- FR-G15 Demo Mode: virtual mesh, offline queueing, auto-sync, scenarios, Mesh Lab UI

## Non-Functional
| ID | Requirement |
|---|---|
| NFR-1 | Fully functional with no internet |
| NFR-2 | Gateway runs on Raspberry Pi 5 (8 GB) with Qwen2.5-1.5B Q4 (extraction/scoring; agent in `rules`/`hybrid` mode) |
| NFR-3 | SOS packet ≤ 200 bytes core payload (BLE-friendly, fragmentable) |
| NFR-4 | Mobile battery ≤ 8%/hr with relay enabled (target) |
| NFR-5 | Triage latency p95 < 5s (1.5B) / < 20s (7B on laptop) |
| NFR-6 | Apache-2.0 license; no proprietary runtime dependencies |
| NFR-7 | Accessibility: large targets, high contrast, Nepali localization |
| NFR-8 | Test coverage ≥ 70% on gateway core and mesh protocol |
| NFR-9 | Agent run p95 < 30s (7B, laptop); falls back to rules within 5s of a failure |
| NFR-10 | Demo Mode needs no hardware and starts in < 1 min |
| NFR-11 | README documents each model and its consuming file/function (CI-checked) |

## Constraints
- Open-weight models only; licenses documented
- No telemetry
