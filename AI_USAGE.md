# AI Usage Disclosure

Rahat uses a local language model to turn free-text reports into structured
needs and to choose among feasible response options. AI also helps interpret
SOS messages and road notices. It does not approve a dispatch, verify a road,
or confirm that supplies arrived.

This disclosure describes the current implementation, checked on 25 October
2026. It does not treat the build brief's proposed features as finished work.

## Model and shared call function

The default model is **`qwen2.5:3b`**, served by Ollama at
`http://localhost:11434`. Both values are configurable through `OLLAMA_MODEL`
and `OLLAMA_URL`; keep the URL local for the documented offline setup.
No closed-provider AI client or remote AI fallback is part of this path.

All tasks below call **`generate_json`** in [ai/client.py](ai/client.py).
It passes a Pydantic JSON schema to Ollama, validates the response, applies
task-specific checks where supplied, retries once on failure, and then uses a
schema-validated rule fallback. Calls are serialized within each backend event
loop, not across separate backend processes.

The wrapper returns `(validated_output, source)`. `source=ai` means a model
response passed validation; `source=fallback` means rules produced the result.
Some no-work paths return `rules` without calling the model. Model, task,
prompt version, latency, validation result and fallback use are recorded in
`AICallLog`. A valid schema is not proof that the interpretation is correct.

## Functions That Use AI

Every task uses the configured model above. The producer is the function that
requests model output; the consumer is where application code uses that output.

| Task | Producer Function and File | Consumer Function and File | Actual Effect |
|---|---|---|---|
| Report extraction | `parse_report` in [ai/report_tasks.py](ai/report_tasks.py) | `create_report` in [backend/app/routers/reports.py](backend/app/routers/reports.py) | Uses extracted categories, urgency, skills and quantities to create unverified `Need` rows when incident/location context resolves. Stores missing fields and follow-up questions with the report. |
| Skill mapping | `map_need_skills` in [ai/volunteer_tasks.py](ai/volunteer_tasks.py) | `resolve_need_skills`, then `match_need` or `propose_ai_assignment`, in [backend/app/routers/assignments.py](backend/app/routers/assignments.py) | When a need lacks skills, chooses names from the controlled skill list. Code uses them to filter eligible volunteers. |
| Match choice | `choose_match_candidate` in [ai/volunteer_tasks.py](ai/volunteer_tasks.py) | `propose_ai_assignment` in [backend/app/routers/assignments.py](backend/app/routers/assignments.py) | Selects one of the top three supplied candidates. Code creates a proposed assignment and linked `AIProposal`. |
| Supply choice | `choose_allocation_stock` in [ai/resource_tasks.py](ai/resource_tasks.py) | `propose_ai_allocation` in [backend/app/routers/resources.py](backend/app/routers/resources.py) | Selects a valid stock option for a draft allocation. Approval rechecks stock; code controls quantity and unit. It does not choose a multi-provider split. |
| Coordination cycle | `run_coordination_cycle` in [ai/coordinator.py](ai/coordinator.py) | `_create_draft_proposal` in the same file; exposed by `coordinate` in [backend/app/routers/coordination.py](backend/app/routers/coordination.py) | Selects up to five assignment/allocation actions from at most twenty supplied candidates. Code persists drafts, not autonomous dispatches. |
| SOS interpretation | `interpret_sos_event` in [ai/sos_tasks.py](ai/sos_tasks.py) | `interpret_sos_event` in the same file | Uses category, urgency and skills to enrich an already-saved SOS and link/create a need when usable incident/location context exists. An explicit user category and urgency override are respected. |
| Road-update extraction | `parse_road_update` in [ai/road_tasks.py](ai/road_tasks.py) | `create_road_update`, then human-triggered `verify_road_update`, in [backend/app/routers/routing.py](backend/app/routers/routing.py) | Stores parsed notices for review. Only verification with coordinates creates a verified blockage that affects estimated routes. |
| Duplicate judgment | `judge_duplicate_reports` in [ai/intelligence_tasks.py](ai/intelligence_tasks.py) | `scan` in [backend/app/routers/situation.py](backend/app/routers/situation.py), with `judge_duplicates=true` | Stores `same_event`, confidence and rationale in a borderline duplicate flag's evidence. Does not merge or delete reports. |
| Exposure assessment | `explain_exposure` in [ai/exposure_tasks.py](ai/exposure_tasks.py) | `incident_exposure` in [backend/app/routers/exposure.py](backend/app/routers/exposure.py) | Adds assessments and a validated attention order for supplied locations. Code computes exposure scores, evidence and geography. |

### Explanation-Only Uses

These are implemented AI features, but they should not be presented as autonomous
decisions or proof that core operations require a model.

| Task | Producer Function and File | Consumer Function and File | Effect |
|---|---|---|---|
| Match explanations | `explain_match_candidates` in [ai/volunteer_tasks.py](ai/volunteer_tasks.py) | `match_need` in [backend/app/routers/assignments.py](backend/app/routers/assignments.py), with `explain=true` | Attaches reasons to returned candidates; does not change their code-computed ranking. |
| Bottleneck explanations | `explain_bottleneck` in [ai/intelligence_tasks.py](ai/intelligence_tasks.py) | `list_bottlenecks` in [backend/app/routers/situation.py](backend/app/routers/situation.py), with `explain=true` | Adds an explanation and suggested action to up to five returned flags. Does not send notifications or execute the suggestion. |
| Recovery narrative | `write_recovery_narrative` in [ai/intelligence_tasks.py](ai/intelligence_tasks.py) | `recovery_report` in [backend/app/routers/situation.py](backend/app/routers/situation.py) | Adds a narrative to computed statistics; does not change fulfilled quantities or delivery evidence. |

## What Happens Without AI

SOS persistence, UUID retry handling, permissions, matching arithmetic and the
receipt ledger remain available. Report parsing falls back to keywords and
regular expressions. Skill mapping uses rules, choices use deterministic
options, and explanations use templates. These fallbacks are less contextual,
but they can still produce needs and proposals. We do not claim that removing
AI makes all operations impossible.

The intended AI contribution is better interpretation of messy messages and
contextual selection among valid options. The recorded evaluation has **not
yet demonstrated that improvement**: the keyword baseline scored 20/30 exact
category sets (66.67%); all five attempted live-model cases timed out into
fallback. AI-only accuracy is unavailable. See [docs/AI_EVALUATION.md](docs/AI_EVALUATION.md).

## Coordinator Scope and Safety

The coordinator sees need descriptions, urgency, remaining quantities,
candidate skills, score breakdowns, estimated travel times and stock options.
It does not receive the full situation summary or run an iterative tool loop.
Its only action types are assignment and allocation proposals. There is no
confidence-based auto-approval, general notification tool, resource procurement
tool, model-training loop, embedding index or retrieval-augmented generation.

Assignment approval requires a manager and rechecks feasibility; the volunteer
must then accept. Allocation approval rechecks stock. `low`, `medium` and
`high` are model-supplied labels, not calibrated probabilities. Human review is
still needed for semantic errors and incomplete evidence.

## Runtime AI Versus Development Assistance

This document names AI that runs inside Rahat. AI assistance used to write code
or documentation is a separate disclosure question under the event's rules.
This documentation was revised with GitHub Copilot assistance and checked
against the current source. That is not a live-model benchmark or a claim of
hackathon eligibility. Confirm the organizer's current rules before submission.
