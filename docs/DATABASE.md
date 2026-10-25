# Database

## Mobile (drift/SQLite)
```sql
CREATE TABLE identity(
  id INTEGER PRIMARY KEY CHECK (id=1),
  pub_key BLOB NOT NULL, priv_key_ref TEXT NOT NULL, display_name TEXT, lang TEXT DEFAULT 'en'
);
CREATE TABLE outbox(
  msg_id BLOB PRIMARY KEY, type INTEGER, payload BLOB, created_at INTEGER,
  state TEXT CHECK(state IN('queued','relayed','at_station','acked','failed')),
  last_hop_count INTEGER
);
CREATE TABLE relay_cache(
  msg_id BLOB PRIMARY KEY, raw BLOB, ttl INTEGER, first_seen INTEGER, forwarded_count INTEGER DEFAULT 0
);
CREATE INDEX idx_relay_seen ON relay_cache(first_seen);
CREATE TABLE inbox(
  msg_id BLOB PRIMARY KEY, type INTEGER, payload BLOB, received_at INTEGER, read INTEGER DEFAULT 0
);
CREATE TABLE peers(
  peer_id TEXT PRIMARY KEY, rssi INTEGER, last_seen INTEGER, hops_to_station INTEGER
);
CREATE TABLE volunteer_profile(
  id INTEGER PRIMARY KEY CHECK(id=1), skills TEXT, has_vehicle INTEGER, vehicle_type TEXT,
  capacity INTEGER, available INTEGER
);
CREATE TABLE tile_packs(id TEXT PRIMARY KEY, region TEXT, path TEXT, bytes INTEGER, updated_at INTEGER);
```

## Gateway (SQLite + SpatiaLite)
```sql
CREATE TABLE devices(
  id TEXT PRIMARY KEY,           -- short id from pubkey
  pub_key BLOB UNIQUE NOT NULL, role TEXT CHECK(role IN('citizen','volunteer','coordinator','station')),
  trust_score REAL DEFAULT 0.5, first_seen INTEGER, last_seen INTEGER, revoked INTEGER DEFAULT 0
);

CREATE TABLE reports(            -- immutable raw ingests
  id INTEGER PRIMARY KEY, msg_id BLOB UNIQUE NOT NULL, device_id TEXT REFERENCES devices(id),
  received_at INTEGER, hops INTEGER, lat REAL, lon REAL, loc_accuracy_m REAL,
  category_hint TEXT, raw_text TEXT, lang TEXT, raw_packet BLOB,
  source TEXT DEFAULT 'mesh'      -- 'mesh' | 'wifi' | 'usb' | 'demo'
);

CREATE TABLE incidents(          -- clustered, enriched
  id INTEGER PRIMARY KEY, status TEXT CHECK(status IN('new','triaged','assigned','en_route','resolved','false_alarm')) DEFAULT 'new',
  category TEXT, people_affected INTEGER, needs TEXT,         -- JSON array
  hazards TEXT,                                               -- JSON array
  priority REAL, priority_explanation TEXT, ai_confidence REAL,
  lat REAL, lon REAL, first_report_at INTEGER, last_update INTEGER,
  assigned_count INTEGER DEFAULT 0, human_override TEXT
);
CREATE TABLE incident_reports(
  incident_id INTEGER REFERENCES incidents(id), report_id INTEGER REFERENCES reports(id),
  similarity REAL, PRIMARY KEY(incident_id, report_id)
);
CREATE TABLE embeddings(report_id INTEGER PRIMARY KEY, vec BLOB, model TEXT);

CREATE TABLE volunteers(
  id INTEGER PRIMARY KEY, device_id TEXT REFERENCES devices(id), name TEXT, skills TEXT, -- JSON
  vehicle_type TEXT, capacity INTEGER, lat REAL, lon REAL, available INTEGER, last_seen INTEGER
);
CREATE TABLE assignments(
  id INTEGER PRIMARY KEY, incident_id INTEGER REFERENCES incidents(id),
  volunteer_id INTEGER REFERENCES volunteers(id),
  status TEXT CHECK(status IN('proposed','sent','accepted','declined','arrived','done','cancelled')),
  eta_min REAL, route_geojson TEXT, score REAL, proposed_by TEXT, confirmed_by TEXT, created_at INTEGER
);

CREATE TABLE road_obstructions(
  id INTEGER PRIMARY KEY, geom_wkt TEXT, reported_by TEXT, source_report_id INTEGER,
  severity TEXT, active INTEGER DEFAULT 1, created_at INTEGER, cleared_at INTEGER
);
CREATE TABLE resources(
  id INTEGER PRIMARY KEY, kind TEXT, quantity REAL, unit TEXT, depot_lat REAL, depot_lon REAL, updated_at INTEGER
);
CREATE TABLE bottlenecks(
  id INTEGER PRIMARY KEY, kind TEXT CHECK(kind IN('supply','route','coverage','staffing')),
  area_geojson TEXT, severity REAL, summary TEXT, evidence TEXT, detected_at INTEGER, resolved INTEGER DEFAULT 0
);
CREATE TABLE ai_runs(
  id INTEGER PRIMARY KEY, agent TEXT, model TEXT, input_hash TEXT, output TEXT, valid INTEGER,
  latency_ms INTEGER, fallback_used INTEGER, created_at INTEGER
);

-- Dispatcher agent
CREATE TABLE agent_sessions(
  id INTEGER PRIMARY KEY, incident_id INTEGER REFERENCES incidents(id),
  trigger TEXT, model TEXT, mode TEXT,
  status TEXT CHECK(status IN('running','awaiting_approval','completed','failed','fallback')),
  summary TEXT, decision TEXT,                 -- JSON FinalDecision
  started_at INTEGER, ended_at INTEGER, steps_used INTEGER
);
CREATE TABLE agent_steps(
  id INTEGER PRIMARY KEY, session_id INTEGER REFERENCES agent_sessions(id), n INTEGER,
  tool TEXT, tier TEXT, args TEXT, result TEXT, ok INTEGER, policy_decision TEXT,
  latency_ms INTEGER, created_at INTEGER
);
CREATE TABLE agent_notes(
  id INTEGER PRIMARY KEY, incident_id INTEGER REFERENCES incidents(id),
  session_id INTEGER, note TEXT, created_at INTEGER
);
CREATE INDEX idx_agent_steps_session ON agent_steps(session_id, n);

CREATE TABLE audit_log(
  id INTEGER PRIMARY KEY, ts INTEGER, actor TEXT, action TEXT, entity TEXT, entity_id TEXT, detail TEXT, prev_hash TEXT, hash TEXT
);
CREATE TABLE users(  -- dashboard accounts
  id INTEGER PRIMARY KEY, username TEXT UNIQUE, pw_hash TEXT, role TEXT, created_at INTEGER
);
CREATE INDEX idx_inc_priority ON incidents(status, priority DESC);
```

## Notes
- `reports` is append-only; `incidents` is derived and rebuildable.
- `agent_steps` is append-only; assignments created by the agent have `proposed_by='agent:<session_id>'`.
- `audit_log` is hash-chained for tamper evidence.
- Demo Mode state is in memory (no tables); packets it ingests go through the normal `reports` table flagged `source='demo'`.
- Retention: purge raw location after N days post-resolution (configurable).
- Migrations: Alembic (gateway), drift migrations (mobile).
