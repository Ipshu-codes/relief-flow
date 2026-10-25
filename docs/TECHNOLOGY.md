# Technology

Rahat runs as one Python backend, a public Flutter app, and a separate Flutter
Service Station. The local build does not need a JavaScript dashboard, Docker,
or a road-routing server.

| Area | Technology | Role |
|---|---|---|
| Public app and Service Station | Flutter, Dart, Material | SOS intake and coordinator workflows; both use the same API |
| Client state and connectivity | Provider, HTTP, shared_preferences, UUID, geolocator | UI state, durable SOS outbox, retry identity and optional measured GPS |
| Native BLE integration | flutter_blue_plus and Android platform code | Native relay integration; not evidence of a working end-to-end hardware deployment |
| API | Python 3.11+, FastAPI, Uvicorn | Validated HTTP endpoints and role-aware operations |
| Database | SQLAlchemy 2, SQLite, Alembic | Shared operational records and schema migrations |
| Authentication | PyJWT HS256, pwdlib Argon2 | Expiring access tokens, password hashing and backend role checks |
| Local inference | Ollama Python client; default `qwen2.5:3b` | Structured extraction, bounded choices and explanations |
| Output contracts | Pydantic v2 | JSON schemas, type checks and task-specific validation |
| Background work | FastAPI background tasks, APScheduler | Post-save SOS interpretation and deterministic bottleneck scans |
| External data | httpx, JSON snapshots, CSV/GeoJSON imports | Timed fetches, saved-response fallback and attributed imports |
| Transport protocol | CBOR/RMP, Ed25519 signatures | Signed-packet validation; distinct from proving radio delivery |
| Matching | Fixed weighted scoring and feasibility checks | Code ranks candidates; AI can select only supplied options |
| Routing | Haversine distance, projection and geometric detours | Estimated distance/time; not navigation on a road graph |
| Verification | pytest, pytest-asyncio, FastAPI TestClient, Flutter tests/analyzer | Workflow and contract checks; separate from live-model evaluation |

## How AI Is Integrated

All runtime model requests go through `generate_json` in
[../ai/client.py](../ai/client.py). It uses Ollama's `generate` API with a
Pydantic schema in `format`, temperature `0.1`, a task timeout and one retry.
After failed attempts, a validated rule fallback returns a labelled result.
There is no LangGraph, LangChain or autonomous tool-calling framework in this
path. The coordinator uses a single structured selection, followed by code
that creates draft proposals.

The default local endpoint is `http://localhost:11434`. `OLLAMA_MODEL` and
`OLLAMA_URL` configure the model and server. Use a local open-weight model,
not a cloud tag, for the setup described here. No fine-tuning, model training,
embedding search or retrieval index is implemented.

Serial inference is scoped to one backend event loop. Multiple workers can
still compete for the same model server. Task timeouts and retries mean a
request may wait longer than one timeout interval.

See [../AI_USAGE.md](../AI_USAGE.md) for exact functions and
[AI_EVALUATION.md](AI_EVALUATION.md) for the measured timeout behavior.

## Why This Stack

SQLite and a single backend keep the local demo practical. Flutter shares
client code between mobile and the station, while separate entry points keep
public intake apart from operational controls. Ollama keeps model requests on
the station machine. Pydantic contracts make a small model's output usable by
code without giving it authority over stock or dispatch approvals.

These choices simplify a prototype, not a production emergency deployment.
PostgreSQL/PostGIS, GraphHopper, OSRM, OR-Tools, street-level offline tiles,
LoRa hardware relay and on-device AI are not part of the current runtime.
See [LIMITATIONS.md](LIMITATIONS.md) for the remaining engineering work.
