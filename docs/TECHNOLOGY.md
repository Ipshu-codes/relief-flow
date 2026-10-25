# Technology actually used

| Area | Implementation |
|---|---|
| Frontend | Flutter/Dart, Material 3, dark original-platform palette |
| State/network | Provider, HTTP, shared_preferences, UUID, geolocator |
| API | Python 3.11+, FastAPI, Uvicorn |
| Persistence | SQLAlchemy 2 and SQLite; Alembic adoption migration |
| Authentication | PyJWT HS256; pwdlib Argon2 password hashes |
| Local AI | Ollama Python client, `qwen2.5:3b`, Pydantic schema validation |
| Background | FastAPI background tasks; APScheduler bottleneck scans |
| Packet transport | Inherited RMP CBOR codec, Ed25519 signatures, TTL |
| Matching | Deterministic feasibility and weighted scoring; model choice among valid options |
| Routes | Haversine/projection estimates and geometric blockage detours |
| Tests | pytest, pytest-asyncio, TestClient, Flutter tests and analyzer |

The old platform's dark colors are retained: background `#0D1114`, surface
`#151B1F`, primary green `#4CAF7D`, warning yellow `#FBC02D`, SOS red `#D32F2F`.
The emergency UI uses large category buttons, optional details, honest location
availability and a single send/retry action. Protected operational data stays
under Response/Volunteer rather than crowding the public SOS screen.

PostgreSQL/PostGIS, OR-Tools, OSRM, live OSM tiles, on-device inference and real
BLE/Meshtastic forwarding are not activated by this implementation. Do not list
them as deployed technology. The legacy GraphHopper/MCP experiments remain in
the original folder but are not the canonical runtime.
