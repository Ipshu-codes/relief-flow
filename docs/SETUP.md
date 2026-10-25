# Setup

## Prerequisites
| Tool | Version |
|---|---|
| Python | 3.11+ |
| Flutter | 3.24+ (Dart 3.5+) |
| Node | 20+ (dashboard) |
| Ollama | latest |
| Java | 17+ (GraphHopper) |
| Docker | optional |

## 1. Clone
```bash
git clone https://github.com/<org>/rahat && cd rahat
```

## 2. Gateway
```bash
cd gateway
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
python scripts/gen_station_keys.py     # creates station keypair + enrollment QR
```

## 3. Local AI
```bash
ollama serve &
ollama pull qwen2.5:7b-instruct        # Dispatcher (Standard: laptop 16GB)
ollama pull qwen2.5:1.5b-instruct      # extraction/scoring (Lite: Pi)
ollama pull nomic-embed-text           # embeddings
# optional: ollama pull llama3.1:8b  /  ollama pull phi3:mini
```
`.env`:
```
RAHAT_MODEL=qwen2.5:1.5b-instruct
RAHAT_AGENT_MODEL=qwen2.5:7b-instruct
RAHAT_EMBED_MODEL=nomic-embed-text
RAHAT_LLM_URL=http://127.0.0.1:11434
AGENT_MODE=hybrid              # llm | hybrid | rules  (Pi: rules or hybrid)
AGENT_MAX_STEPS=6
AUTO_DISPATCH=false            # true only for drills/demos
AUTO_DISPATCH_MIN_PRIORITY=85
DEMO_MODE=false
RAHAT_MOCK_LLM=false           # true for dev without a model
```

## 4. Offline geo data (routing)
Requires **Java 17+** and internet **once**. Everything runs offline afterwards.

```bash
make fetch-geo           # ~450 MB: Nepal OSM extract + GraphHopper 11.1 jar
make graphhopper-import  # optional: pre-build the routing graph (several minutes)
make graphhopper         # serve on http://127.0.0.1:8989
make graphhopper-status  # verify the router is reachable
```

Point the gateway at it in `.env` (default already matches):

```bash
RAHAT_ROUTER_URL=http://127.0.0.1:8989
```

If the router is unreachable the gateway falls back to straight-line (haversine)
ETAs, so development and demos never break.

To use a smaller region while testing (Monaco is a few hundred KB):

```bash
make fetch-geo GH_OSM_URL=https://download.geofabrik.de/europe/monaco-latest.osm.pbf
```

See `infra/graphhopper/README.md` for memory tuning, the config, and how to add
foot/bike profiles.

### Offline map basemap
The dashboard and the Flutter app draw Nepal from committed GeoJSON — no tile
server and no internet at runtime:

```bash
python scripts/build_map_assets.py             # rebuild from cached downloads
python scripts/build_map_assets.py --download  # re-download from geoJSON-Nepal (MIT)
```

Outputs: `dashboard/data/{nepal_states,nepal_hq}.geojson` and the same files in
`mobile/assets/` (declared in `pubspec.yaml`). Street-level tiles (MBTiles/PMTiles)
remain a separate step and are not built by `fetch-geo`.

## 5. Run gateway
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
python -m app.mcp_server --http --port 8001   # optional MCP
```

## 6. Dashboard
The gateway serves the zero-build dashboard itself (no npm step):
```bash
make gateway
# open http://127.0.0.1:8000/
```
The map plots each incident at the coordinates in its SOS packet, and reloads
from `/api/v1/incidents` every 10 s plus on WebSocket `incident.created`.

## 7. Mobile
```bash
cd mobile
flutter pub get
dart run build_runner build
flutter run             # Android device recommended for BLE
```
Android: grant Bluetooth scan/advertise/connect + location permissions. The SOS
screen requests a fresh GPS fix and shows coordinates + accuracy before sending;
if no fix is available it falls back to the Kathmandu valley centre and labels
the report approximate.

### Connecting a real phone
The app's default `http://127.0.0.1:8000` only works on the station machine.
On a phone on the same Wi-Fi/hotspot:

```bash
make gateway-lan      # binds 0.0.0.0:8000
hostname -I           # station IP, e.g. 192.168.1.42
```

Then in the app: **Settings → Command station URL → `http://192.168.1.42:8000`**.
The Android manifest allows cleartext HTTP for this local-network case (there
is no TLS on the station); BLE mesh traffic is unaffected.

## 8. Demo Mode (no hardware)
```bash
make demo        # sets DEMO_MODE=true, starts the gateway + dashboard, opens Mesh Lab
make eval-agent  # run Dispatcher scenarios
```
See [DEMO_MODE.md](DEMO_MODE.md).

## 9. Load-test simulator (standalone)
```bash
cd simulator && python run.py --nodes 50 --loss 0.2 --gateway http://localhost:8000
```

## Raspberry Pi 5 profile
```bash
sudo apt install bluez python3-venv openjdk-17-jre
# use infra/pi/setup.sh: sets up the systemd services (gateway, ollama, graphhopper, hotspot)
```
Set `AGENT_MODE=rules` or `hybrid`. Run it as a Wi-Fi hotspot (`Rahat-Station`) so dashboards on nearby laptops can connect.

## Docker (dev)
```bash
docker compose -f infra/docker-compose.yml up
```

## Troubleshooting
| Symptom | Fix |
|---|---|
| LLM slow on Pi | Use a Q4 1.5B model; cut context; `RAHAT_MAX_TOKENS=256`; `AGENT_MODE=rules` |
| No BLE peers | Check permissions; disable battery optimization; use a USB BLE dongle on the station |
| Invalid JSON from the model | Confirm the Ollama version supports `format`; check `ai_runs` for fallback |
| Agent loops / invalid tool calls | Use qwen2.5:7b; lower temperature; check `agent_steps`; set `AGENT_MODE=hybrid` (falls back to the matching engine) |

## Makefile targets
`setup · gateway · dashboard · mobile-run · demo · test · lint · eval · eval-agent · simulate · fetch-geo`
