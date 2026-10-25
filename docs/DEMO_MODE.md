# Demo Mode: Simulated Offline Mesh

Showing a live BLE/LoRa mesh in a video or on stage depends on hardware, radio
conditions, and OS permissions. **Demo Mode** puts a virtual mesh *inside the
gateway* so anyone can see how messages queue offline and sync when a peer
reconnects, with no hardware.

> Demo Mode simulates **only the radio**. It uses the real packet codec
> (signing, TTL, dedupe), the real ingest pipeline, the real AI agents, and the
> real dashboard. It is clearly labeled "SIMULATION" in the UI.

## Run
```bash
make demo                      # DEMO_MODE=true: gateway + dashboard + virtual mesh
# or
DEMO_MODE=true uvicorn app.main:app --port 8000
```
Open the dashboard → **Mesh Lab** tab.

## What you can do in Mesh Lab
- See a graph of virtual nodes: phones, volunteers, relay nodes, a LoRa node, and the Station.
- **Toggle a node or link offline/online** (simulates leaving range, battery death, a collapsed road).
- **Send an SOS** from any node (choose category, text, location).
- Watch packets hop (animated), with TTL and the hop count.
- Watch each node's **outbox/relay queue** fill while it has no path to the Station.
- Reconnect the node and watch an **automatic sync** flush the queue in priority order, the Station ingest, the AI triage, the Dispatcher trace, and the ACK travel back.
- Adjust **packet loss %**, **latency**, **LoRa payload cap**, and playback speed (1×/5×/20×).

## Store-and-forward and sync model
Each virtual node holds:
```
outbox        own unsent packets
relay_cache   packets heard from others (24h TTL)
seen_ids      dedupe set
```
**Opportunistic sync (anti-entropy):** when two nodes become connected, they
exchange a compact summary of `msg_id`s (a Bloom filter or hash list), then send only
the packets the other side lacks, in priority order (SOS > ACK/ASSIGN > BEACON).
Duplicates are dropped by `msg_id`. When any node reaches the Station, the packet is
ingested through the normal `/ingest` path.

```
A(offline) ──✕── B ──── C ──── Station
A sends SOS → queued in A.outbox (state: queued)
A reconnects to B → sync → B.relay_cache → C → Station
Station ingests → AI triage → ACK → back along the reverse path
```

## LoRa realism
The `SimTransport` supports profiles:
| Profile | Max payload | Notes |
|---|---|---|
| `ble` | ~244 B (fragmentable) | Default phones |
| `lora_sf7` | ~222 B | Fast, shorter range |
| `lora_sf12` | ~51 B | Slow, long range; forces the compact packet format |

Packets exceeding the cap are fragmented or sent in the compact variant (short sender id, truncated
payload). The simulator shows airtime and duty-cycle delay so the constraints are visible.

## Scenarios
`demo/scenarios/*.yaml`, one-click in the UI:
| Scenario | Shows |
|---|---|
| `quake_kathmandu` | 30 nodes, 12 SOS in 2 min, duplicates merged, queue prioritized |
| `river_cutoff` | A village node isolated; queue builds; a boat volunteer reconnects → sync |
| `road_blocked` | Obstruction added; Dispatcher reroutes volunteer; ETA change shown |
| `supply_gap` | Depot nearly out of rice; the bottleneck flagged with a recommendation |

### Suggested 90-second demo script
1. (0:00) Load `river_cutoff`. Show the village node cut off.
2. (0:10) Send 3 SOS from the village: they queue (state `queued`, nothing arrives).
3. (0:25) Toggle the bridge link online → sync animation → Station receives all 3.
4. (0:40) AI triage fills the queue; show the duplicate merge and priority scores.
5. (0:55) Open the Dispatcher trace: tools called, a reroute around a blocked road.
6. (1:10) Click **Approve** → ASSIGN packet routes back; the SOS sender's status becomes *Help assigned*.

## Implementation
```
gateway/app/demo/
├── engine.py        # discrete-event loop (nodes, links, scheduler, speed control)
├── nodes.py         # VirtualNode (outbox, relay_cache, sync)
├── transport.py     # SimTransport (ble / lora profiles, loss, latency, cap)
├── scenarios.py     # YAML loader
└── api.py           # /demo/* routes (mounted only if DEMO_MODE=true)
```
Reuses `protocol/codec.py` and `ingest/`. No separate code paths for packets.

### API
| Method | Path | Description |
|---|---|---|
| GET | `/demo/state` | Nodes, links, queues, clock, params |
| POST | `/demo/nodes/{id}/toggle` | Online/offline |
| POST | `/demo/links/{a}/{b}/toggle` | Cut or restore a link |
| POST | `/demo/sos` | `{ "node": "n7", "category": "trapped", "text": "…" }` |
| POST | `/demo/params` | `{ "loss": 0.2, "latency_ms": 300, "profile": "lora_sf7", "speed": 5 }` |
| POST | `/demo/scenarios/{name}/load` | Load a scenario |
| POST | `/demo/reset` | Reset |

WebSocket events (on `/ws/stream`): `mesh.node_state`, `mesh.packet_hop`, `mesh.queue_update`, `mesh.sync_started`, `mesh.sync_completed`.

## Tests
- Property test: no packet loops; TTL always decreases.
- Determinism: a seeded run gives identical delivery results.
- Sync test: isolate → send → reconnect → all packets arrive exactly once.

## Safety
Demo data is synthetic. `DEMO_MODE` cannot be enabled together with production keys (the gateway
refuses to start if a real station key is present without `--allow-demo-with-keys`).
