# Limitations and future improvements

This is a working local hackathon prototype, not certified emergency infrastructure.
It cannot guarantee response, safety, availability or help arrival.

1. **Physical radio:** no verified end-to-end BLE/Meshtastic/LoRa deployment.
   The local SOS outbox retries while the SOS screen is open and on resume,
   with an explicit retry button as well. Closed-app background delivery is not
   implemented. Mesh Lab is a labelled in-memory bridge simulation. Gateway
   batch intake preserves written addresses, but compact signed RMP packets
   cannot carry an unlimited address without fragmentation/reassembly.
2. **Routes:** geometric estimates and synthetic detours, not road-network
   navigation. GraphHopper code is preserved historically but not activated.
3. **Database:** SQLite local deployment, not tested PostgreSQL/PostGIS or
   distributed concurrency. Alembic adopts the current module schema and adds
   contact info and structured SOS addresses; it is not a universal historical-data merger.
4. **AI:** small local models can misparse language, invent semantic details or
   time out. Schema/ID validation limits action surfaces but does not prove
   semantic correctness. Human review remains essential. Inference fallback
   must stay visibly labelled. No closed remote provider fallback.
5. **Language:** English and Romanized Nepali are primary AI inputs; Nepali UI
   translation is partial. No claim of full Nepali-script model accuracy.
6. **External sources:** adapters/snapshots exist, but no verified current
   district-wide census, BIPAD/DHM or OSM dataset is bundled as live truth.
   Demo baselines are synthetic and labelled. Real imports need attribution,
   licensing and snapshot dates.
7. **Location:** unavailable GPS is accepted honestly, with a written address
   and landmark fallback. Receipt-protected later GPS updates keep that address.
   GPS has finite accuracy, and later fixes describe the device's current
   position, not necessarily the original emergency site. Web GPS needs location
   permission and HTTPS/localhost. Automatic SOS-to-need linking requires a
   usable incident and nearby recorded location; it may remain unlinked until
   a coordinator supplies context. It does not geocode an arbitrary written address.
8. **Accounts:** public demo credentials are local-only. Password reset,
   account invitation/email verification and enterprise identity are future work.
   Employee initial passwords must be shared through an appropriate private
   channel. No credentials are hardcoded into production authentication.
9. **Browser storage:** local outbox/receipts use preferences and can be removed
   by browser-data clearing. JWTs are memory-only. Capability receipt tokens
   must not be shared publicly.
10. **Deployment:** HTTPS, network policies, tuned rate limiting, monitoring,
    backups, production authorization review, load/concurrency testing and
    operational disaster-response validation are required before public use.
11. **Coverage and staffing:** recommendations use recorded needs/skills/windows;
    inaccurate or incomplete records cannot establish actual manpower sufficiency.
    Multi-provider global optimization and OR-Tools are not implemented.
12. **Submission evidence:** automated mocks are not live model benchmarks.
    See the evaluation report for actual tested model coverage and failures.
13. **Emergency calls:** the listed numbers are for Nepal only. `tel:` links
    request the device's calling app, not an automatic call or a confirmed
    dispatch. Telephone coverage and a compatible calling app are required.
    Ambulance availability varies. Real emergency calls and physical-phone
    dialer launches have not been exercised during automated testing.

Next priorities: road graph integration, durable background jobs, audited data
imports, verified radio framing/reassembly/ACKs, database concurrency hardening,
broader language evaluations and accessibility/user testing with responders.
