# Original-platform feature integration

The original `Rahat-A-disaster-response-platform/` is retained with Git history
and files. Its prior modifications were not discarded. The separately preserved
`miscellaneous/legacy-platform` copy is also retained. The canonical frontend
was derived from its connected mobile app, not the unrelated light-colored
request-storage prototype.

| Original feature | Canonical integration |
|---|---|
| Dark mobile design, red SOS, green actions | Preserved in Flutter theme; simplified public help screen |
| Category SOS + optional note | Unified `/sos`; stable UUID, durable local retry, real GPS/manual/unknown location |
| Written location fallback | Nested district/city/ward/road/landmark; offline persistence, gateway batch intake and coordinator display |
| GPS after reconnect | Receipt-protected enrichment of the same SOS, accuracy/timestamp and reuse of saved interpretation for need linking |
| Emergency calls | Nepal police/ambulance/fire/tourist-police `tel:` links below SOS; explicit no-dialer feedback |
| Delivery timeline | Actual receipt-token polling and coordinator acknowledgement/dispatch/resolution |
| Packet codec, signatures, TTL, dedupe | `protocol/`; `/api/v1/ingest/packet` verifies then writes shared SOS events |
| Mesh Lab/offline simulation | Coordinator Mesh Lab: disconnect bridge, queue signed SOS, reconnect into shared receiver |
| Priority incidents and map detail | Shared needs with urgency, verification, confidence, location and progress; no fake map tiles |
| Volunteer profiles | Existing JWT-scoped profiles, contact info, multi-skills, availability and employee registration |
| Matching engine | Existing stricter skill/window/travel validation; AI chooses among valid candidates |
| Dispatcher/approval concept | Shared AI proposals, reasons/source and human approval with revalidation |
| Obstructions and rerouting | Shared verified blockages and estimate-routing detours; never real-road navigation claims |
| Resource stock and supply gaps | Reservation, partial confirmations, remaining quantities and bottleneck scans |
| AI extraction/scoring/dedupe/insights | Shared AI parser/urgency, duplicate judge, exposure, bottleneck and recovery services |
| Model/audit trace | Shared `ai_call_log`, `ai_proposals`, rationale/source, hash-linked audit trail |
| Settings/language | Automatic shared connection; English UI and selected Nepali SOS labels |
| BLE service code | Preserved source; not advertised as complete transport |
| MCP, satellite/LoRa, live map tiles | Historical/unfinished experiments preserved, not claimed as integrated runtime |

## Important compatibility differences

- The old gateway's `incidents` represented grouped SOS reports; canonical
  `incidents` represent disaster events and `needs` represent response requests.
  Existing databases are not copied together blindly or silently reset.
- New packet/SOS traffic reaches the canonical `sos_events` and `needs`, not a
  parallel gateway database. Signed packets use a deterministic UUID derived
  from sender and message ID.
- Do not run both gateways on port 8000. The single canonical backend serves
  the compiled Flutter app and API.
- The simulation is deliberately labelled and in-memory. It demonstrates
  store-and-forward behavior, not a physical mesh deployment.
- Legacy endpoint names are retained only where explicitly documented
  (signed packet ingestion and demo paths), not as a promise of complete old API
  binary compatibility.
