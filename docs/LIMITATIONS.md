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
   The recorded 30-case keyword baseline scored 66.67% exact category sets.
   All five live-model cases returned fallback after timeouts; there were
   no validated AI responses. A longer single-case attempt also failed to
   complete within its outer deadline. AI-only accuracy and a three-model
   comparison remain unavailable. See [AI_EVALUATION.md](AI_EVALUATION.md).
13. **Emergency calls:** the listed numbers are for Nepal only. `tel:` links
    request the device's calling app, not an automatic call or a confirmed
    dispatch. Telephone coverage and a compatible calling app are required.
    Ambulance availability varies. Real emergency calls and physical-phone
    dialer launches have not been exercised during automated testing.

14. **Coordinator scope:** only assignment/allocation candidate selection is
   implemented, not the build brief's general tool registry. The prompt does
   not contain the full situation summary. Confidence labels do not trigger
   auto-approval and are not calibrated success probabilities.
15. **Feedback:** outcomes are stored, but scorer weights, dedupe rules and
   model parameters do not learn from them. A lower open-need count after
   delivery is state tracking, not model improvement.
16. **Follow-up and notifications:** parsed missing fields/questions are
   stored, not an automatic conversation. SOS notification fan-out exists,
   but the coordinator cannot choose a general notify-volunteer action.
   SMS requires a configured provider and credentials; delivery is not
   guaranteed and is separate from model inference.
17. **AI dependence:** rule fallbacks can still create needs and proposals.
   The measured results do not yet show a model quality advantage. The build
   brief's eligibility test must be discussed with the organizer rather
   than treated as satisfied by having an Ollama call.

## Future Improvements

| Priority | Work | Evidence Needed Before Claiming It |
|---|---|---|
| First | Resolve local inference timeouts and compare candidate models | Completed `source=ai` responses, latency and matched AI-versus-baseline scores |
| Next | Feed situation summaries, hazards and bottlenecks into coordination | Tests showing that relevant evidence changes a valid proposal |
| Next | Add notification and priority-change proposal actions | Permission, duplicate-action, audit and approval tests |
| Next | Collect reviewed outcome and duplicate labels | A versioned evaluation set with consent/privacy controls; dispatch success alone is not a dedupe label |
| Later | Evaluate outcome-informed scoring | Held-out improvement without unacceptable subgroup or safety regressions |
| Later | Restricted opt-in automatic approval | Calibrated confidence, hard eligibility checks, concurrency protection and operator controls; retain volunteer consent |
| Later | Road-graph routing, durable jobs and database hardening | Field-valid routes, job recovery and concurrent-load tests |
| Later | Audited data imports and physical relay | Verified licences/dates and end-to-end radio receipts, respectively |

RAG, open-model embeddings, satellite flood mapping and LoRa hardware are not
implemented. Future features are not part of the current demo's evidence.
