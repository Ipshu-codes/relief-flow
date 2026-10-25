# Authentication & Security

## Threat model
| Threat | Impact | Mitigation |
|---|---|---|
| Spoofed or spam SOS | Wasted resources | Ed25519-signed packets, device enrollment, per-device rate limits, trust score |
| Replay | Duplicate dispatch | `msg_id` + timestamp window (±24h) + dedupe |
| Eavesdropping on location | Privacy harm | Payload encrypted to the station's X25519 key (sealed box); relays see only the header |
| Malicious relay (drop/flood) | Delivery loss | Redundant paths, TTL cap, neighbor suppression, flood-rate limits |
| Compromised/stolen device | Fake identity | Revocation list pushed via mesh BEACON, coordinator can revoke |
| Prompt injection via report text | Manipulated AI | Quoted data, schema-constrained output, tool allowlist, human confirm for irreversible actions |
| Excessive agency (agent acts wrongly) | Bad dispatch | Tiered tools, T2 needs approval, step/time caps, allowlist, audit |
| Tool-argument injection via report text | Wrong tool args | JSON-schema validation, policy engine outside the model, quoted data |
| Malicious MCP client | Unauthorized actions | Scoped tokens, T2 confirmation token, rate limits, LAN-only |
| Demo Mode in production | Fake data in real ops | Refuses to start with real station keys; "SIMULATION" banner; `source='demo'` tag |
| Dashboard takeover | Full control | Strong passwords, JWT with short TTL, LAN-only, optional WPA3 hotspot |
| Station theft | Data exposure | Full-disk encryption, panic wipe |

## Device identity
- On first launch: generate an Ed25519 keypair (private key in Keychain / Android Keystore).
- **Anonymous mode** (default): the pubkey is the identity, no PII required.
- **Enrollment** (volunteers/coordinators): the station issues a short code (QR) → the device posts its pubkey → the station assigns a role. Enrollment can be done offline via QR scan.
- Citizens may send SOS un-enrolled. Packets get a lower default trust and stricter rate limits.

## Packet crypto
- Signing: Ed25519 (`cryptography` / `pynacl` in Python, `cryptography` package in Dart).
- Confidentiality: libsodium sealed box (X25519 + XSalsa20-Poly1305) to the station public key; the key is distributed via QR and beacon.
- Directed messages (ASSIGN/ACK) are encrypted to the recipient's key.
- TTL is excluded from the signed region so relays can decrement it.

## Dashboard / API auth
### Implemented (`gateway/app/security/auth.py`, `gateway/app/api/auth.py`)
- Passwords: PBKDF2-SHA256, 100k iterations, 16-byte random salt per password, stored as
  `salt$iterations$digest`.
- Access tokens: HMAC-SHA256 signed (JWT-shaped), 15 min TTL, `RAHAT_AUTH_SECRET` signing key.
  Expired or tampered tokens are rejected.
- Roles: `viewer`, `coordinator`, `admin`; enforced with `require_role(...)` FastAPI dependencies.
- Endpoints: `POST /api/v1/auth/register`, `POST /api/v1/auth/login`,
  `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`.
- Token revocation on logout is not implemented (tokens simply expire); plan is a server-side
  deny-list if that becomes necessary.

### Planned (not yet built)
- Argon2id password hashing (PBKDF2 is stdlib-only today, no extra dependency).
- Refresh tokens (12 h) — today clients re-login when the 15 min token expires.
- Rate limiting (`slowapi`) on `/auth/login` and `/auth/register`.
- Local-only CORS policy and optional HTTPS via a self-signed local CA.
- All writes recorded in `audit_log` (the agent policy engine audits today; auth writes do not yet).

## Agent permissions
| Tier | Examples | Who can trigger | Approval |
|---|---|---|---|
| T0 | read tools | agent, MCP `read` | none |
| T1 | propose_dispatch, flag_bottleneck | agent, MCP `coordinator` | none, but logged and reversible |
| T2 | send_assignment | coordinator only | human confirmation (or `AUTO_DISPATCH` in drills) |

## Trust scoring
`trust = base(role) + 0.1*confirmed_reports − 0.2*false_alarms`, clipped 0..1. Multiplies the priority score; low trust → "verify" badge, never auto-suppressed.

## Privacy
- Data minimization: only category, coordinates, short text, and an optional contact alias.
- Retention policy and panic wipe documented and tested.
- No analytics, no third-party calls, and the model runs locally.

## AI-specific security
- Models are pulled from verified hashes (checksums in `models.lock`).
- LLM endpoint bound to `127.0.0.1`.
- The audit log is hash-chained: `hash = SHA256(prev_hash || canonical(entry))`.

## Secure development
- Dependabot, `pip-audit`, `flutter pub outdated`, secret scanning, signed commits for maintainers, and a `SECURITY.md` with a disclosure process.

## Known limitations
- BLE is not a hardened channel. Metadata (timing, device presence) is observable.
- iOS background relay is constrained by the OS.
