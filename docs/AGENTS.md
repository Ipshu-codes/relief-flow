# AI Agents

Rahat has two kinds of AI components:

1. **Pipeline agents** (single-shot, schema-constrained): Extractor, Scorer, Dedupe, Bottleneck Analyst, Sitrep.
2. **The Dispatcher Agent** (tool-calling loop): decides what to look up and what to propose, holds context, and takes policy-gated actions.

All entry points live in `gateway/app/ai/` (see AI_USAGE_DISCLOSURE.md).

## Common rules
- Temperature ≤ 0.2; JSON-schema-constrained output; validated with Pydantic.
- 1 retry on invalid output, then deterministic fallback.
- Prompts live in `ai/prompts/` (versioned headers).
- Every run is logged to `ai_runs`; agent loops also log each step to `agent_steps`.
- Report text is always passed as quoted data, never as instructions.
- Low confidence (< 0.5) → flagged "needs human review".

```python
class AgentResult(BaseModel):
    output: dict
    confidence: float          # 0..1
    explanation: str           # one sentence
    fallback_used: bool
    model: str
```

---

## 0. Dispatcher Agent: `ai/dispatcher.py` (tool-calling)

### What it does
When an incident needs a response decision, the Dispatcher reasons about it and
**chooses which tools to call**, in what order, based on what earlier tool results say.

**Triggers**
| Trigger | Example |
|---|---|
| `incident.triaged` with priority ≥ 70 | New critical incident |
| `obstruction.created` | Road blocked on an active route |
| `assignment.declined` / `assignment.timeout` | Volunteer cannot go |
| `bottleneck.detected` (severity high) | Zone with no coverage |
| Manual (dashboard "Ask agent" / MCP) | Coordinator asks "who can reach Bhaktapur?" |

### Tools (shared registry: `gateway/app/tools/registry.py`)
| Tool | Args | Tier | Effect |
|---|---|---|---|
| `get_incident` | `id` | T0 read | Incident detail + reports |
| `list_open_incidents` | `bbox?, min_priority?` | T0 | Nearby open incidents |
| `count_available_volunteers` | `skill?, center, radius_km` | T0 | Count and skill breakdown (**queries the local DB**) |
| `find_volunteers` | `incident_id, skills?, radius_km?` | T0 | Ranked candidates |
| `calculate_route` | `from, to, profile` | T0 | Offline GraphHopper route + ETA, respecting obstructions |
| `check_obstructions` | `bbox` | T0 | Active blocked roads |
| `get_resource_stock` | `kind?` | T0 | Depot stock |
| `remember` | `incident_id, note` | T1 | Saves a note to incident memory |
| `propose_dispatch` | `incident_id, volunteer_ids[], reason` | T1 write | Creates `assignments` with status `proposed` (reversible) |
| `flag_bottleneck` | `kind, area, summary` | T1 write | Creates a `bottlenecks` row |
| `escalate_to_human` | `incident_id, reason` | T1 write | Raises a dashboard alert |
| `send_assignment` | `assignment_id` | **T2 irreversible** | Sends ASSIGN packet into the mesh |

### Action policy
| Tier | Policy |
|---|---|
| T0 (read) | Runs automatically |
| T1 (reversible write) | Runs automatically, always logged, shown as "AI proposed" |
| T2 (irreversible, leaves the station) | Requires coordinator approval via `POST /agent/sessions/{id}/approve`. Auto-runs **only** if `AUTO_DISPATCH=true` **and** `priority ≥ AUTO_DISPATCH_MIN_PRIORITY` (demo and drill setting, off by default) |

The model can only call tools in the allowlist. Arguments are validated against
JSON schemas, and the policy engine runs outside the model.

### Loop
```python
async def run(incident_id: int, trigger: Trigger) -> AgentSession:
    session = sessions.open(incident_id, trigger)
    messages = build_context(session)          # system + incident + memory + trigger
    for step in range(settings.AGENT_MAX_STEPS):          # default 6
        reply = await llm.chat(model=settings.AGENT_MODEL, messages=messages,
                               tools=registry.schemas(), options={"temperature": 0.1})
        if not reply.tool_calls:
            break                                          # model decided it is done
        for call in reply.tool_calls:
            result = policy.execute(call, session)         # validate → tier check → run → log
            messages += [reply, tool_message(call, result)]
            sessions.log_step(session, step, call, result)
    decision = FinalDecision.model_validate(extract_final(reply))  # summary, actions, confidence
    return sessions.close(session, decision)
```
Guards: max steps, per-run timeout, duplicate-call detection, invalid-call retry
(1×), then **deterministic fallback**: `matching/engine.py` (Hungarian assignment)
creates the same `proposed` assignments without the LLM.

### Context and memory
- **Working context:** the message history inside a run (tool results feed the next decision).
- **Incident memory:** `agent_sessions.summary` and `agent_notes` carry forward, so a re-trigger (e.g., road blocked) starts from "what we already decided and why".
- **Situation context:** compact digest of open incidents and bottlenecks injected into the system prompt, trimmed to the model's context budget.

### Example trace
```
Trigger: incident 41 triaged (priority 92, "children trapped, collapsed building")
1. get_incident(41)                          → 4 people, needs rescue+medical
2. count_available_volunteers(skill=rescue, center=incident, radius_km=5) → 3
3. find_volunteers(41, skills=[rescue,first_aid]) → V12, V7, V19
4. calculate_route(V12 → incident)           → 14 min, car
5. check_obstructions(bbox)                  → Ring Road segment blocked
6. calculate_route(V12 → incident, avoid)    → 26 min  (rerouted)
FinalDecision: propose_dispatch(41, [V7, V12]) — V7 is 9 min away via the north road;
               V12 is the only first-aider. confidence 0.78. Awaiting approval.
```

### Output
```json
{ "summary": "…", "actions_taken": ["propose_dispatch#118"], "needs_human": true,
  "confidence": 0.78, "reasoning": "one or two sentences" }
```

### Model requirements
Default `qwen2.5:7b-instruct` (Ollama tool-calling, Apache-2.0). Optional `llama3.1:8b`.
On the **Lite (Pi)** profile the Dispatcher runs with a reduced toolset and the
1.5B model, or in `rules` mode (fallback only); extraction and scoring still use
the LLM. Set `AGENT_MODE=llm|hybrid|rules`.

### Agent evaluation (`make eval-agent`)
Scenario set in `eval/agent_scenarios/`: tool-selection accuracy, invalid-call
rate, steps per task, task success (correct volunteer set), and the policy
violation count (must be 0).

---

## 1. Extractor Agent: `ai/extractor.py`
**Input:** raw text (EN/NE/mixed), category hint, GPS, timestamp.
**Output:**
```json
{ "category": "trapped|medical|fire|flood|food_water|shelter|missing|road_blocked|other",
  "people_affected": 4, "vulnerable": ["children","elderly","injured"],
  "needs": ["rescue","medical"], "hazards": ["collapse"],
  "location_text": "near Boudha stupa", "road_obstruction": null }
```
**Fallback:** keyword/regex rules + category hint.
```
SYSTEM: You extract structured data from disaster distress messages in Nepali or English.
Output ONLY JSON matching the schema. If unknown, use null. Do not invent facts.
USER: <message> ...
```

## 2. Priority Scorer: `ai/scorer.py`
```
score = 0.35*severity + 0.20*vulnerability + 0.15*people_factor
      + 0.15*time_unserved + 0.10*isolation + 0.05*corroboration  (× trust_multiplier)
```
LLM supplies `severity` and `vulnerability` (1–5) with justification; the rest is
computed deterministically. Output includes the term breakdown.

## 3. Dedupe/Cluster Agent: `ai/dedupe.py`
1. Candidates: reports within 300 m and 60 min.
2. Embedding cosine similarity (`nomic-embed-text`) + category match.
3. LLM adjudication only for borderline pairs (0.70–0.85).
4. Merge into an incident; track `report_count`.
**Fallback:** TF-IDF + geo/time proximity.

## 4. Matching engine: `matching/engine.py` (+ `ai/match_explainer.py`)
Deterministic Hungarian assignment (ETA, skills, capacity, load). It is the **fallback and
verifier** for the Dispatcher: the agent's proposals are checked against it (e.g., a
volunteer lacking a boat is rejected for a flood incident). The LLM explains pairs and flags conflicts.

## 5. Bottleneck Analyst: `ai/bottleneck.py`
Runs every 5 min and on demand. Deterministic signals (unserved incidents by zone, burn-rate
vs stock, repeated blockages, volunteer-to-incident ratio per H3 cell) are clustered by the
LLM into labeled bottlenecks with recommended actions. It also parses free-text logistics
notes ("rice stock at Bhaktapur depot nearly finished").

## 6. Sitrep Writer: `ai/sitrep.py`
Summarizes the last N hours; used by the dashboard and the MCP resource.

## Evaluation
`make eval` reports extraction F1, dedupe precision/recall, priority rank correlation, and latency per
model. `make eval-agent` covers the Dispatcher. Coordinator edits are exported as opt-in anonymized eval data.

## Safety
- Prompt injection: report text is quoted data; outputs are schema-validated; tools are allowlisted; the policy engine sits outside the model.
- **Excessive agency:** the model never gets T2 tools without approval; step and time caps; every action audited.
- The AI never deletes records or touches the audit log.
