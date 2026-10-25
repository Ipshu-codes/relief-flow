# AI architecture and programmatic-use disclosure

## Shared runtime

Model: **`qwen2.5:3b`**, local Ollama, configurable with `OLLAMA_MODEL`.
The installed model name is not proof that every call used AI: every result
must retain its `source` and call-log evidence. One wrapper,
`ai/client.py::generate_json`, supplies JSON schemas, validates with Pydantic
and task-specific option/skill validators, retries once, logs attempts, and
uses explicitly labelled deterministic fallbacks. Calls are serialized within
each backend event loop to limit local memory contention.

No model training or fine-tuning. No OpenAI, Anthropic, Gemini, closed embeddings
or remote inference fallback.

## Exact consumers

| Task | AI entry point | Programmatic consumer and effect |
|---|---|---|
| Messy report extraction | `ai/report_tasks.py::parse_report` | `backend/app/routers/reports.py::create_report` consumes parsed categories, urgency, quantities, controlled skills and vulnerable groups to create **unverified** shared `Need` rows and store missing fields/questions |
| Need-to-skill mapping | `ai/volunteer_tasks.py::map_need_skills` | `backend/app/routers/assignments.py::resolve_need_skills` passes allowed skill names into deterministic feasibility matching; output changes eligible candidates |
| Match explanation | `ai/volunteer_tasks.py::explain_match_candidates` | `backend/app/routers/assignments.py::match_need` attaches reasons without letting the model change code ranking |
| Match choice | `ai/volunteer_tasks.py::choose_match_candidate` | `backend/app/routers/assignments.py::propose_ai_assignment` selects only an offered candidate and persists a proposed assignment and linked AI proposal |
| Supply choice | `ai/resource_tasks.py::choose_allocation_stock` | `backend/app/routers/resources.py::propose_ai_allocation` selects a valid stock row for a draft. `approve_ai_allocation` revalidates and calls `allocate_stock`; code controls quantity and units |
| Coordination cycle | `ai/coordinator.py::run_coordination_cycle` | Its validated selection is consumed by `_create_draft_proposal` in the same file to persist candidate-backed proposals; `backend/app/routers/coordination.py::coordinate` exposes them for human review |
| Command station coordination | `backend/app/routers/command_station.py::coordinate_incident` | Runs `run_coordination_cycle` over shared backend state for an incident; proposals are labelled `source=ai` or `source=fallback` and broadcast to the WebSocket stream for human review |
| SOS interpretation | `ai/sos_tasks.py::interpret_sos_event` | The function itself consumes validated category/urgency/skills, updates the **already saved** SOS and links/creates an unverified need only with known incident/location context |
| Exposure assessment | `ai/exposure_tasks.py::explain_exposure` | `backend/app/routers/exposure.py::incident_exposure` consumes explanations and validated attention order; evidence scores and coordinates stay code-owned |
| Road-update extraction | `ai/road_tasks.py::parse_road_update` | `backend/app/routers/routing.py::create_road_update` persists pending parsed road notices; `verify_road_update` requires coordinator coordinates before creating a verified blockage |
| Duplicate judgment | `ai/intelligence_tasks.py::judge_duplicate_reports` | Shared situation/bottleneck scanning consumes confidence/verdict on borderline candidates to inform duplicate evidence and flags |
| Bottleneck explanation | `ai/intelligence_tasks.py::explain_bottleneck` | `backend/app/routers/situation.py::scan` attaches explanation and next-action evidence to code-detected flags |
| Recovery narrative | `ai/intelligence_tasks.py::write_recovery_narrative` | `backend/app/routers/situation.py::recovery_report` combines it with actual aggregate statistics, never replacing confirmed receipt math |

## Product dependence and resilience

The intended AI value is **unstructured text -> structured needs -> skill
mapping -> validated options -> explained proposal -> human approval**.
Deleting model calls removes the contextual parsing and trade-off choices;
basic keyword/rank-one fallbacks remain deliberately available so emergency
intake is not blocked. This resilience is not a claim that AI is indispensable
to storing a request. Judges should inspect actual model-vs-fallback evidence
in [AI_EVALUATION](AI_EVALUATION.md), including language failures and coverage.

Model outputs never grant roles, verify reports/skills, invent route geometry,
modify stock arithmetic or confirm a delivery. An assignment proposal is not a
confirmed response. Human approval and field-confirmed outcomes are separate.

## Evidence boundaries

Automated integration tests validate both model-failure and supplied-schema
success paths. They are not proof of real-model quality. The evaluation runner
records actual local inference and fallback provenance separately.
