# Rahat AI Layer: Hackathon Build Brief

*Give this to your AI coding assistant for all AI work. Researched 24 Oct 2026. Items marked **VERIFY** were found through third-party projects or from memory, not official documentation. Test them with curl before building on them.*

## 1. What this brief is for

The backend (auth, Modules 1 to 3) is largely built. What is missing is the part judges will score: AI doing real work inside the system. This brief consolidates the hackathon rules, the open-model options for an 8 GB Windows laptop, the free Nepal data sources, and a step-by-step plan for the AI layer.

## 2. Hackathon rules, consolidated

### Eligibility checklist (every item is required)

- Public GitHub repository with everything needed to run and understand the solution.
- Documentation: README, architecture overview, technology details, and limitations / future improvements.
- Working demo of the key capabilities.
- Short demo video or presentation: problem, solution, workflow, value.
- Qualifies as 'Build with AI' (see core test below).
- AI Usage Disclosure: a short written statement naming the exact file and function where AI output is consumed programmatically.

### The core test

If you deleted the AI call from the codebase, would the product still do its job? If yes, it does not qualify. AI must process, decide, or act on something the rest of the system depends on.

### What counts as meaningful AI

- **Structured extraction:** AI reads unstructured input and outputs JSON that code consumes.
- **Decision or routing logic:** AI classifies or scores, and the system acts differently on the result.
- **Tool or function calling:** AI selects and invokes tools, and results are fed back.
- **Multi-step pipeline:** one AI output feeds the next step.
- **Retrieval-grounded reasoning (RAG):** answers conditioned on data the system retrieved.
- **Data transformation at scale:** AI processes batches of records, then code aggregates or scores them.

### Tooling rules

- **Use:** local or self-hosted inference (Ollama, LM Studio, vLLM), open-weight models (Llama, Mistral, Qwen, DeepSeek and similar, run locally or through a hosted inference provider), and open-source agent frameworks.
- **Skip:** OpenAI, Anthropic, Google Gemini, Azure OpenAI and similar paid closed APIs.
- This covers the **whole pipeline**, including embeddings and small helper classifiers.
- **VERIFY on the official Guidelines page** (frogtoberfest.lftechnology.com/guidelines): whether using an AI coding assistant to write your code is allowed, and what they say about hosted open-weight inference. The rules above are about the product's runtime pipeline, but confirm before you rely on that reading.

### What this means for Rahat's design

1. **The AI path must be the main path, not a hidden extra.** Our earlier rule 'everything works without AI' stays for resilience (SOS must always save), but the fallback should be deliberately basic (keyword rules). The product's value, turning messy messages into needs and decisions, must come from the model. If a keyword fallback could do everything, judges will say the AI is removable.
2. **Prove the AI adds value with numbers.** Run the same eval set through the AI parser and the keyword fallback and report both accuracies in the README. This is the strongest evidence for the core test.
3. **No closed API anywhere, even as an optional fallback.** Keep every call going through one wrapper pointing at Ollama.
4. **The reference pattern (Munder Difflin):** an orchestrator reads requests, routes work, escalates only what needs a human, and its output drives real actions. Rahat's equivalent is the **Coordinator agent**, which reads the situation, proposes actions through tools, and escalates approvals to a coordinator.

## 3. Where AI does real work (this table becomes your AI Usage Disclosure)

Fill in the real file and function names once built. Each row must be true: the output is parsed and used by code, not just displayed.

| # | AI task | Input | Consumed by (file::function) | Effect in the system | Without AI |
| --- | --- | --- | --- | --- | --- |
| 1 | Report parser | Raw message, English or Romanized Nepali | `app/ai/parsers.py::parse_report` then `needs` service | Creates Need rows, sets urgency, fills `missing_fields` which triggers follow-up questions | Messages cannot become needs |
| 2 | Skill mapper | Need description | `matching.py::filter_candidates` | Decides which volunteers are eligible | No skill filter |
| 3 | Road-update parser | Pasted Nepal Police or Dept. of Roads update text | `blockages.py::create_from_parsed` | Creates blockage records that change route and ETA results | No road status feed |
| 4 | SOS interpreter | Free-text SOS | `sos.py::link_or_create_need` | Sets category and urgency, links or creates a need | SOS stays unlinked |
| 5 | Coordinator agent | Situation snapshot (needs, volunteers, stock, blockages, hazards) | `app/ai/coordinator.py::run_cycle` then `tool_executor` | Calls tools that create draft proposals and notifications | No proactive coordination |
| 6 | Match chooser | Top 3 code-ranked candidates per need | `proposals.py::create_assignment_proposal` | Selects who is proposed | Rank 1 is always picked |
| 7 | Allocation chooser | Valid stock options per need | `proposals.py::create_allocation_proposal` | Selects the provider split | Nearest-first only |
| 8 | Duplicate judge | Borderline report pairs | `reports.py::apply_duplicate_verdict` | Merges or flags duplicates | Threshold only |
| 9 | Bottleneck explainer | Flag evidence | `bottlenecks.py::attach_explanation` | Drives notifications and next-action suggestions | Template text |

**Multi-step pipeline to show in the demo:** raw text, then parser, then skill mapper, then code builds candidates, then chooser, then a proposed assignment, then human approval, then delivery tracking.

**Optional retrieval step (stretch):** embed a small set of relief standards and past incident notes with an open embedding model, and let the Coordinator retrieve the relevant passages before it proposes (for example, water per person per day). Keep this small and only add it after everything else works.

## 4. Open models and tools for an 8 GB Windows laptop

Running a model uses RAM next to VS Code and the browser, so stay small. Sizes below are approximate.

| Model (Ollama tag) | Approx. size | Role | Notes |
| --- | --- | --- | --- |
| `qwen2.5:3b` | \~2 GB | Main candidate | Reliable at JSON output; supports tool calling in Ollama (VERIFY on your install) |
| `qwen3:4b` | \~2.5 GB | Alternative main model | Has a thinking mode; turn it off for parsing (`think=false`) or it will be slow and wordy |
| `llama3.2:3b` | \~2 GB | Second opinion | Documented as supporting both tool calling and structured outputs in Ollama |
| `qwen3:1.7b` or `llama3.2:1b` | \~1 to 1.4 GB | Emergency option if the laptop struggles | Noticeably less accurate; rely more on code-validated options |
| `nomic-embed-text` | \~0.3 GB | Embeddings (duplicates, retrieval) | Open model, allowed under the rules |

**How to choose:** do not guess. Build the eval set first (Step 2), run `qwen2.5:3b`, `qwen3:4b` and `llama3.2:3b` through it, and keep the one with the best accuracy that responds in a few seconds on your machine. Record the comparison in the README.

**Do not use** the Ollama `...-cloud` model tags for the core pipeline. They run on remote servers, which breaks the offline story, and the rules are stricter about hosted use than local use.

**Techniques that make small models dependable**

- Pass the Pydantic JSON schema to Ollama's `format` field (structured output) and validate again in code.
- Temperature 0 to 0.2, short prompts, few-shot examples (2 to 3 Romanized Nepali examples), and at most 3 to 5 options for any choice.
- Never ask the model to calculate. Give it numbers and ask it to choose or explain.
- Run one model call at a time on an 8 GB machine. Queue background AI work.

**Agent loop: write it by hand.** A plain loop (snapshot, model returns a validated tool call, code checks it, executes the draft action, logs it) is easiest to explain and disclose. Open-source frameworks such as Pydantic AI, LangGraph or smolagents can talk to Ollama, but they add weight and make the disclosure harder; only use one if it clearly saves time.

## 5. Free government and open data sources

There is no single government API that gives 'affected areas plus local population'. The realistic setup combines these:

| Need | Source | Access | Notes |
| --- | --- | --- | --- |
| Disaster incidents (floods, landslides, other hazards) with location, deaths, injuries, houses affected, verified flag | **BIPAD Portal** (NDRRMA, Government of Nepal) | `https://bipadportal.gov.np/api/v1/incident/` (public, no key seen in use). Public projects add parameters such as `expand=loss,event,wards,hazard`, `ordering=-incident_on`, `incident_on__gt=<date>` | **VERIFY.** Found through public GitHub projects, not official docs. Reported quirks: the `count` field can be a meaningless huge number, so use the length of `results`; pagination completeness is not guaranteed, so follow `next` links |
| River levels | BIPAD `api/v1/river/` (DHM gauges) and DHM river watch at hydrology.gov.np | Public projects read both | **VERIFY.** No documented official API found; some projects scrape the DHM site |
| Rainfall observations | BIPAD rain stations (`api/v1/` rain endpoint, VERIFY exact path) | Public | Same caveat |
| Admin areas (province, district, municipality, ward) | BIPAD admin endpoints, plus Survey Department boundaries on HDX (COD-AB, CC BY-IGO) | Download or API | Use ward IDs to join incidents to wards |
| Population and households per ward | **Nepal NSO data portal** (data.nsonepal.gov.np), Census 2021 | CSV and XLSX downloads, datasets at province, district, local level and ward level | The census reports down to ward level. Download the files for your demo district; this is a file import, not a live API. Total households nationally were about 6.67 million |
| Rain forecast | Open-Meteo forecast API | No key, free for non-commercial use | Model forecast, not an official warning |
| River discharge forecast | Open-Meteo Flood API (GloFAS model, about 5 km grid) | No key | Modelled, not measured. Coordinates must sit on or very near a river or you get nothing useful |
| Roads, bridges, buildings, health posts, schools | OpenStreetMap through the HOT Export Tool | Download once per district as GeoJSON | Use for the road network and facility locations |
| **Road blocked or open** | **No official open API found.** Nepal Police and the Department of Roads publish blockage updates as press and social posts | Coordinator pastes the text into Rahat; the AI parses it (AI task 3) | Always store as `unverified` until a coordinator confirms, and expire it after N hours |

**Important operating rules for external data**

- Put every fetch behind an adapter with a timeout, and save raw responses to `data/raw/` with a timestamp. The demo must run from saved snapshots if the portal is slow or down.
- Cache responses and be gentle with request rates. Check the portal's terms before heavy use.
- BIPAD has records from this month, so you can demo with **real recent incidents**, not only old ones.
- Treat all external data as **reported or estimated**. Only coordinator-verified records become verified.

## 6. How affected areas are worked out (code first, AI explains)

For every ward or settlement, code builds an evidence record. The model never decides geography.

1. **Incident signal:** BIPAD flood or landslide incidents in the last N days that match the ward ID or fall within a set distance.
2. **River signal:** nearest DHM gauge above its warning or danger level.
3. **Forecast signal:** Open-Meteo rain or discharge above a threshold.
4. **Report signal:** number of community reports and SOS events relative to the ward's baseline households.
5. **Output per location:** `exposure_level` (none, watch, likely, confirmed), `estimated_households` (census), `reported_households`, `verified_households`, `confidence`, and the evidence list.
6. **AI's job:** read the evidence list and write the assessment sentence and recommended attention order. The Coordinator may then propose volunteers and supplies for locations at `likely` or above.

Example: 'Ward 7: about 180 households (census estimate). Flood incident reported yesterday (BIPAD, verified). Gauge upstream above warning level. 60 families reported needing water (unverified).'

## 7. Step-by-step plan for the AI layer

Order matters. Finish each step, run its tests, then move on.

**Step 0: Audit and shared records.** List every table that stores needs, reports and audit entries across Modules 1 to 3 and merge them into one shared `needs`, `raw_reports`, `audit_log`, `ai_proposals`, `ai_call_log`. *Done when:* modules read and write the same need records.

**Step 1: AI core wrapper.** One `generate_json` function that calls Ollama with the schema in `format`, a timeout, one retry, Pydantic validation and logging of model, prompt version and latency. All AI goes through this, so no closed API can sneak in. *Done when:* a test shows a schema failure triggers one retry and then the fallback.

**Step 2: Eval set first.** Write 30 messages (English, Romanized Nepali, messy, incomplete, with a few that are not requests at all) with the expected parse. Add a script that prints accuracy for the AI parser and the keyword fallback. *Done when:* both accuracies print.

**Step 3: Report parser (AI task 1).** Versioned prompt, few-shot examples, schema-constrained output, follow-up questions for missing fields. Benchmark the three models here and pick one. *Done when:* '40 families at the school, no drinking water, elderly need medicine' creates need rows, and the model comparison is recorded.

**Step 4: Location and population import.** Import ward boundaries, census households and population for your demo district, and OSM facilities. Join on ward ID or name. *Done when:* a location profile shows 'estimated households' with its source and year.

**Step 5: External data adapters.** BIPAD incidents, river and rain stations, Open-Meteo, each with timeout, raw snapshot saving and snapshot fallback. *Done when:* the app runs fully from saved snapshots with the network off.

**Step 6: Affected-area estimator.** The code from section 6 plus the AI assessment sentence. *Done when:* the demo district returns exposure levels with evidence.

**Step 7: Road-update parser (AI task 3).** Pasted police or Dept. of Roads text becomes blockage records (road, place text, status: blocked, partial, one-way, night-restricted, time). Coordinator verifies. Blockages expire. *Done when:* pasting a real update changes a route result.

**Step 8: Skill mapper and match chooser (AI tasks 2 and 6).** Code filters and ranks, the model picks among the top 3, the result is a proposed assignment. *Done when:* a need produces an explained proposal a coordinator can approve.

**Step 9: Allocation chooser (AI task 7).** Code builds valid stock options with planning rules (for example 15 litres of water per person per day, a Sphere standard to double check), the model chooses. *Done when:* proposals never exceed stock.

**Step 10: Coordinator agent (AI task 5).** Snapshot builder, draft-only tool registry (`create_need`, `propose_assignment`, `propose_allocation`, `flag_bottleneck`, `request_missing_info`, `notify_coordinator`), tool-call validation, `POST /ai/coordinate`, scheduled and event-triggered cycles, approve and reject endpoints. *Done when:* one cycle on the demo data produces several useful proposals with reasons.

**Step 11: SOS, duplicate and bottleneck AI (tasks 4, 8, 9).** Background only, never blocking SOS saving. *Done when:* with Ollama off, SOS still saves; with it on, SOS is linked to needs.

**Step 12: Stretch: retrieval.** Small embedding index (`nomic-embed-text`) over relief standards and past incidents, used by the Coordinator. Skip if time is short.

**Step 13: Proof and paperwork.** Fill `AI_USAGE.md`, final eval numbers, README, architecture diagram, demo script, video.

## 8. Rules for the coding assistant

1. Code decides, the model chooses among validated options and explains. The model never changes quantities, stock, statuses, coordinates, permissions or routes.
2. Every model output is validated against a Pydantic schema before use.
3. Every proposal is a draft until a human approves it.
4. All AI calls go through the one wrapper, which only talks to the local Ollama server. No OpenAI, Anthropic, Gemini or other closed APIs, including for embeddings.
5. Remaining need equals requested minus confirmed received. 'Sent' never closes a need.
6. Estimated, reported and verified data stay separate fields.
7. Every state change and every AI proposal goes to the audit log.
8. One step at a time. List files, tables and endpoints first, then implement, test, and show how to verify. Do not start the next step.
9. If any statement in this brief turns out wrong (an endpoint, a model capability), report it instead of silently working around it.

## 9. AI\_USAGE.md template

Create this file at the repo root. One short entry per AI task:

- **Task:** Report parser
- **Model:** the Ollama model tag you actually use
- **Where the model is called:** `app/ai/client.py::generate_json`
- **Where the output is consumed programmatically:** `app/ai/parsers.py::parse_report` returns a validated `ParsedReport`, and `app/services/needs.py::create_needs_from_report` creates database rows and decides whether to ask follow-up questions
- **What happens if the AI is removed:** reports cannot be converted into needs

Repeat for each row in section 3. Only list tasks that actually exist in the code.

## 10. README and demo checklist

**README must contain:** problem, solution, architecture diagram, tech stack, how to install Ollama and pull the model, how to run the backend, how to seed demo data, how to run tests and the eval script, AI usage summary linking to `AI_USAGE.md`, data sources with licences and snapshot dates, limitations, future improvements.

**Demo script (about 4 minutes):**

1. A messy Romanized Nepali message arrives; show the parsed needs and the follow-up question.
2. Show the ward profile with census households, BIPAD incident and river signal, and the exposure level.
3. Paste a police road update; show the blockage appear and a route change.
4. Run a coordination cycle; show proposed volunteer and supply assignments with reasons.
5. Approve one; confirm a partial delivery; show the remaining need update.
6. Send an offline SOS batch twice; show no duplicates.
7. Show the eval table: AI parser vs keyword fallback.

## 11. Honest limits to state in the README

- Routes are estimates, not real road routing.
- Road status depends on human verification of pasted official updates; no official live feed was found.
- The small local model makes mistakes, especially with Nepali script; Romanized Nepali and English are the supported inputs.
- Census figures are 2021 baselines, not current occupancy.
- BIPAD and DHM data were accessed through unofficial usage of public endpoints; availability and terms can change.
- Satellite flood mapping and LoRa hardware relay are out of scope.

## 12. Kickoff prompt for the AI assistant

```
You are working on the AI layer of Rahat, an open-source disaster response
coordination backend for a hackathon whose rules require that AI does real work
inside the product using ONLY open-weight models run locally (Ollama), with no
closed paid APIs anywhere, including embeddings. Read docs/AI_BRIEF.md fully.
Follow sections 3, 7 and 8 exactly. Work on one step at a time starting with
Step 0 (audit): inspect the existing code, list every table that stores needs,
reports or audit entries, and propose the merge. Do not write code until I say
go. For every step: list files, tables and endpoints first, then implement,
write tests (AI tests must run with Ollama working and mocked as failing), and
show me how to verify. Keep AI_USAGE.md updated with the real file and function
names as you build each AI task. Never let the model change quantities, stock,
statuses, coordinates or routes.
```
