# API (Gateway, FastAPI)

Base URL: `http://<station>:8000/api/v1` · OpenAPI at `/docs`
Auth: `Authorization: Bearer <JWT>` (dashboard/volunteer) or signed-packet (mesh ingest).

## Ingest
| Method | Path | Description |
|---|---|---|
| POST | `/ingest/packet` | Raw RMP packet (base64) from bridge/Wi-Fi/USB |
| POST | `/ingest/batch` | Array of packets (store-and-forward sync) |

**POST /ingest/batch**
```json
{ "packets": ["<b64>", "<b64>"], "via": "wifi-direct" }
```
Response `202`: `{ "accepted": 2, "duplicates": 0, "invalid": 0 }`

## Incidents
| Method | Path | Description |
|---|---|---|
| GET | `/incidents?status=&min_priority=&bbox=` | Prioritized list |
| GET | `/incidents/{id}` | Detail with reports, AI output |
| PATCH | `/incidents/{id}` | Human override (status, priority, category) |
| POST | `/incidents/{id}/merge` | Merge clusters `{ "into": 12 }` |
| POST | `/incidents/{id}/ack` | Send ACK into the mesh |

Example:
```json
{
  "id": 41, "status": "triaged", "category": "trapped",
  "people_affected": 4, "needs": ["rescue","medical"],
  "hazards": ["collapsed_building","aftershock"],
  "priority": 92.5, "ai_confidence": 0.81,
  "priority_explanation": "Children trapped under debris; medical need; no prior response.",
  "lat": 27.7172, "lon": 85.3240, "report_count": 3
}
```

## Volunteers
| Method | Path | Description |
|---|---|---|
| POST | `/volunteers` | Register/update profile |
| GET | `/volunteers?available=true&bbox=` | List |
| POST | `/volunteers/{id}/location` | Update position |

## Matching & Dispatch
| Method | Path | Description |
|---|---|---|
| POST | `/matching/suggest` | `{ "incident_ids": [..] }` → proposed assignments (deterministic engine) |
| POST | `/assignments/{id}/confirm` | Coordinator approves → ASSIGN packet sent |
| PATCH | `/assignments/{id}` | accept/decline/arrived/done |

## Agent
| Method | Path | Description |
|---|---|---|
| POST | `/agent/run` | `{ "incident_id": 41, "trigger": "manual" }` → starts a Dispatcher session |
| GET | `/agent/sessions?incident_id=` | List sessions |
| GET | `/agent/sessions/{id}` | Full trace: steps, tool calls, results, decision |
| POST | `/agent/sessions/{id}/approve` | Approve T2 actions (e.g., send ASSIGN) |
| POST | `/agent/sessions/{id}/reject` | Reject proposals with a reason (logged as eval data) |
| GET | `/agent/config` | Mode (`llm`, `hybrid`, `rules`), model, caps, auto-dispatch flag |

Session example:
```json
{ "id": 77, "incident_id": 41, "status": "awaiting_approval",
  "steps": [ { "n": 2, "tool": "count_available_volunteers",
               "args": {"skill":"rescue","radius_km":5}, "result": {"count":3} } ],
  "decision": { "actions_taken": ["propose_dispatch#118"], "confidence": 0.78 } }
```

## Routing
| Method | Path | Description |
|---|---|---|
| GET | `/route?from=lat,lon&to=lat,lon&profile=car` | Route avoiding obstructions |
| POST | `/obstructions` | Add blocked road `{ "geometry": GeoJSON, "severity": "full" }` |
| DELETE | `/obstructions/{id}` | Clear |
| POST | `/obstructions/{id}/reroute` | Recompute affected assignments |

## Insights
| Method | Path | Description |
|---|---|---|
| GET | `/insights/bottlenecks` | Active bottlenecks |
| GET | `/insights/underserved` | GeoJSON of low-coverage zones |
| POST | `/insights/run` | Trigger analysis now |
| GET | `/insights/summary` | LLM-generated sitrep (markdown) |

## Resources
`GET/POST/PATCH /resources`: depot stock levels.

## System
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Model, DB, mesh bridge status |
| GET | `/ai/runs?agent=` | AI audit trail |
| GET | `/audit?since=` | Audit log |

## Demo (only when DEMO_MODE=true)
See [DEMO_MODE.md](DEMO_MODE.md): `/demo/state`, `/demo/nodes/{id}/toggle`, `/demo/links/{a}/{b}/toggle`,
`/demo/sos`, `/demo/params`, `/demo/scenarios/{name}/load`, `/demo/reset`.

## WebSocket
`/ws/stream` events:
- `incident.created|updated`, `assignment.updated`, `bottleneck.detected`, `mesh.stats`
- `agent.step`, `agent.awaiting_approval`, `agent.completed`
- Demo only: `mesh.node_state`, `mesh.packet_hop`, `mesh.queue_update`, `mesh.sync_started`, `mesh.sync_completed`

```json
{ "event": "incident.updated", "data": { "id": 41, "priority": 92.5 } }
```

## Auth
| Method | Path | Description |
|---|---|---|
| POST | `/auth/login` | `{username,password}` → `{access_token, refresh_token}` |
| POST | `/auth/device/enroll` | Device pubkey enrollment (needs enrollment code) |

## Errors
`{ "error": { "code": "invalid_signature", "message": "...", "request_id": "..." } }`
Codes: `invalid_signature`, `duplicate`, `rate_limited`, `validation_error`, `llm_unavailable` (served via fallback), `forbidden`, `approval_required`.
