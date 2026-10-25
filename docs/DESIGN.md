# Design

## Principles
1. **One thumb, one tap** under stress.
2. **Honest status**: never imply delivery when only queued.
3. **Low power**: dark theme default, minimal animation.
4. **Bilingual**: English / नेपाली toggle on every screen.
5. **Graceful degradation**: every AI feature has a non-AI path.

## Mobile screens
1. **Home**: giant SOS button, mesh status chip (peers nearby, hops to station), battery saver toggle.
2. **SOS flow**: category grid (icons + labels) → optional note → confirm (hold 1s) → status timeline.
3. **Status**: `Queued → Relayed (n hops) → At station → Acknowledged → Help assigned`.
4. **Map**: offline OSM tiles, own position, nearby SOS, station, blocked roads.
5. **Volunteer**: profile, availability toggle, assignment card (accept/decline/arrived/done).
6. **Mesh**: peer list, relayed packet count, storage use.
7. **Settings**: language, tile packs, identity key export, data wipe.

## Dashboard (coordinator)
- Left: **Priority queue** (score, category, age, cluster size, AI badge)
- Center: **Map** with heat layer, clusters, volunteers, blocked edges
- Right: **Detail panel**: raw text, AI extraction, explanation, suggested dispatch, Accept/Override
- Top: station health (model, queue lag, mesh packets/min)
- Tab: **Insights**: bottlenecks, underserved zones, supply gap chart
- **Agent trace panel** (detail view): each step shows the tool, its args, its result, and the policy decision; buttons **Approve / Reject / Re-run**. Proposed items carry a 🤖 chip.
- **Mesh Lab tab** (Demo Mode): node-link graph, toggles for nodes and links, per-node queue badges, packet-hop animation, a scenario picker, and sliders for loss, latency, and speed. A persistent "SIMULATION" banner.

## Visual language
Colors by severity: Critical `#D32F2F`, High `#F57C00`, Medium `#FBC02D`, Low `#388E3C`.
Never use color alone: pair with icon and text. Font ≥ 16sp body.

## AI UX rules
- Label AI-derived fields with a 🤖 chip and confidence.
- Show "why" in one sentence.
- Coordinator can edit any field; edits are logged and used as eval data.
