# Product Requirements Document: Rahat

**Version:** 0.2 | **Status:** Draft | **Owner:** Rahat maintainers

## 1. Problem
In earthquakes, floods, and landslides (common in Nepal), cellular and internet
infrastructure fails exactly when coordination matters most. Responders are
swamped by duplicate, unstructured, unverified reports, and volunteers are
dispatched inefficiently or into blocked routes.

## 2. Vision
A community-deployable, infrastructure-independent platform that turns scattered
distress signals into a prioritized, actionable operational picture.

## 3. Goals
| ID | Goal | Metric |
|---|---|---|
| G1 | Deliver SOS without internet | ≥90% delivery within 10 hops, in simulation |
| G2 | Reduce triage time | Report → priority score < 5s on Raspberry Pi 5 |
| G3 | Reduce duplicates | ≥80% duplicate clusters correctly merged (labeled test set) |
| G4 | Efficient dispatch | Matching suggestion < 3s for 500 volunteers / 200 requests |
| G5 | Open and reproducible | Full setup in < 30 min from README |
| G6 | Agent reliability | ≥85% task success and 0 policy violations on agent scenarios |
| G7 | Demonstrable anywhere | Full offline demo with no hardware in < 2 min |

## 4. Non-Goals
- Replacing official emergency services (112/100/101)
- Internet-dependent cloud features in the core path
- Medical diagnosis
- Unsupervised dispatch outside explicit drill/demo settings (a human confirms irreversible actions)

## 5. Personas
1. **Citizen in distress (Sita)**: low-tech, stressed; needs one-tap SOS.
2. **Volunteer (Ram)**: has skills (first aid, boat, driving); wants relevant nearby tasks.
3. **Field coordinator (Maya)**: runs the command station; needs a prioritized queue and map.
4. **NGO/Local gov logistics lead (Bikash)**: needs bottleneck and coverage insights.
5. **Contributor (you)**: wants a well-documented open-source project.

## 6. User Stories (MVP)
- As Sita, I tap SOS, pick a category, and my alert is relayed even with no signal.
- As Sita, I see delivery status: *queued → relayed → received by station → acknowledged*.
- As Ram, I register skills/vehicle and receive nearby task assignments offline.
- As Maya, I see a live prioritized queue, a map, and AI-proposed dispatches (with the agent's tool trace) I can approve or reject.
- As Maya, I mark a road as blocked and see affected assignments rerouted.
- As Bikash, I see underserved areas and predicted supply shortages.
- As a judge or new contributor, I run a full offline demo with no hardware.

## 7. Scope
**MVP (Frogtoberfest):** SOS + BLE relay, gateway ingest, AI triage, dedupe, dashboard
queue and map, **Dispatcher agent**, volunteer matching, bottleneck report, MCP server,
**Demo Mode (Mesh Lab)**.
**Post-MVP:** Wi-Fi Direct bulk sync, LoRa bridge (hardware), Nepali voice-to-text, multi-station sync,
iOS background relay improvements.

## 8. AI Requirements
- AI is core: extraction → scoring → dedupe → **agentic dispatch** → bottleneck reasoning.
- The Dispatcher must **decide** (choose tools), **use tools** (routing, DB queries, stock), **hold context** (session + incident memory), and **take action** (proposals; gated dispatch).
- Open-weight models only, self-hosted; models and consumption points documented in the README and AI_USAGE_DISCLOSURE.md.
- Deterministic fallback when the model is unavailable or invalid; humans confirm irreversible actions.
- Support Nepali and English input.
- All AI outputs carry `confidence` and `explanation`; agent traces are visible to coordinators.

## 9. Risks
| Risk | Mitigation |
|---|---|
| iOS BLE background limits | Document; Android-first relay; iOS foreground relay |
| Small model hallucination / bad tool calls | Constrained JSON schema, validation, tool allowlist, rules fallback, human-in-loop |
| Agent takes a harmful action | Tiered tools, T2 approval, step caps, audit log |
| False/spam SOS | Signed packets, rate limits, station-side trust scoring |
| Battery drain | Duty-cycled scanning, adaptive TTL |
| Privacy of location | Payload encryption to station key, retention policy |
| 7B model too heavy for Pi | Lite profile uses 1.5B for extraction and `rules`/`hybrid` agent mode |

## 10. Milestones
See [IMPLEMENTATION.md](IMPLEMENTATION.md).
