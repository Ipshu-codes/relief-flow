# Implementation Plan

## Repo structure
```
rahat/
├── mobile/                 # Flutter app
│   └── lib/{core,features/{sos,mesh,map,volunteer,status},data/db}
├── gateway/
│   ├── app/{api,ingest,mesh_bridge,ai,tools,policy,matching,routing,insights,demo,mcp_server.py,db,security}
│   ├── tests/  eval/{datasets,agent_scenarios}
│   └── pyproject.toml
├── dashboard/              # React/Vite or SvelteKit + MapLibre + turf.js (incl. Mesh Lab)
├── infra/{docker-compose.yml, graphhopper/, ollama/, pi/}
├── simulator/              # Standalone mesh simulator CLI (load testing)
├── protocol/               # codec, shared test vectors, categories.json
├── scripts/                # check_disclosure.py, gen_station_keys.py
├── docs/  Makefile  models.lock
```

## Phases (suggested ~4 weeks for the event window)
**Phase 0: Foundations (days 1–2)**
Repo, CI (GitHub Actions: lint, test), license, issue templates, docs skeleton, mock LLM.

**Phase 1: Core pipeline (week 1)**
- RMP packet codec (shared test vectors in `protocol/vectors.json`)
- Gateway ingest + DB + signature verify
- Flutter SOS screen → outbox → loopback transport
- Mesh simulator
- Tool registry + policy engine skeleton (`tools/`, `policy/`), `agent_*` tables, mock LLM that can emit tool calls

**Phase 2: Mesh + AI triage (week 2)**
- BLE transport (Android first), relay rules, ack flow
- Extractor + scorer + fallback rules, `ai_runs` logging
- Dashboard queue + WebSocket
- `DispatcherAgent` with T0 tools (`get_incident`, `count_available_volunteers`, `calculate_route`), step logging, deterministic fallback

**Phase 3: Intelligence (week 3)**
- Dedupe/cluster, matching engine, routing with obstructions
- Bottleneck analyst + sitrep
- Offline map tile packs
- T1/T2 tools, approval flow, reroute trigger, `make eval-agent` scenarios
- Demo Mode engine + Mesh Lab UI + scenarios

**Phase 4: Hardening + polish (week 4)**
- MCP server over the shared registry, auth/RBAC, audit chain
- Agent trace UI, eval suite and benchmarks on Pi
- Demo script recording, README disclosure table verified against code (CI check)
- Docs, demo video, AI Usage Disclosure, release v0.1.0

## Key implementation notes
**Packet codec (Python sketch)**
```python
HEADER = struct.Struct(">BBBB8sI32sH")
def encode(p: Packet, sk: SigningKey) -> bytes:
    body = HEADER.pack(p.ver, p.type, p.flags, p.ttl, p.msg_id, p.ts, p.sender, len(p.payload)) + p.payload
    return body + sk.sign(body).signature
```
Note that TTL is excluded from the signature in a real implementation (relays decrement it). Sign the header with TTL zeroed, or put TTL outside the signed region.

**Extractor call (Ollama)**
```python
resp = await client.chat(model=settings.MODEL, messages=msgs,
    format=ExtractionSchema.model_json_schema(), options={"temperature": 0.1})
data = ExtractionSchema.model_validate_json(resp.message.content)
```

**Tool-calling call (Ollama)**
```python
resp = await client.chat(model=settings.AGENT_MODEL, messages=messages,
    tools=registry.schemas(), options={"temperature": 0.1})
for call in resp.message.tool_calls or []:
    result = policy.execute(call, session)
```

**Matching**
`scipy.optimize.linear_sum_assignment(cost_matrix)`; cost = ETA + penalties for missing skills and overload.

**Testing strategy**
- Unit: codec, relay rules, scorer, matching, policy engine
- Property tests: dedupe and TTL never loop (hypothesis)
- Simulator: 50 nodes, random topology, 20% packet loss → delivery rate
- AI eval: `make eval` thresholds in CI against the mock and a small real model (nightly); `make eval-agent` for the Dispatcher
- Mobile: widget tests plus on-device BLE test checklist

**CI check:** `scripts/check_disclosure.py` fails if a file in `gateway/app/ai/` isn't listed in `AI_USAGE_DISCLOSURE.md`.

## Definition of Done
Tests pass, docs updated, AI paths have fallbacks, no new network calls, and the disclosure file is updated if a model, prompt, or tool changed.
