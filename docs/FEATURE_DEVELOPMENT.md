# Feature Development Guide

## Workflow
1. Pick an issue labeled `frogtoberfest` / `good first issue`. Comment to claim it.
2. Fork → branch: `feat/<area>-<short-name>` or `fix/...`.
3. Develop with tests and docs.
4. Run `make lint test` (and `make eval` / `make eval-agent` if you touched `ai/` or `tools/`).
5. Open a PR using the template; link the issue.
6. Address review; maintainers squash-merge.

## Commits
Conventional Commits: `feat(mesh): add neighbor suppression`.

## Adding a new SOS category
1. Add the enum in `protocol/categories.json`.
2. Mobile: icon + EN/NE strings in `mobile/lib/l10n/`.
3. Gateway: update `ExtractionSchema`, scorer weights, and fallback keywords.
4. Add eval examples (≥10 EN, ≥10 NE).
5. Update the docs.

## Adding / changing an AI agent
1. Create `ai/<name>.py` implementing `BaseAgent` (schema, `run`, `fallback`).
2. Prompts in `ai/prompts/<name>.md` (versioned header).
3. Register in `ai/registry.py`.
4. Add fixtures and eval metrics.
5. **Update `AI_USAGE_DISCLOSURE.md`** (required by CI check).

## Adding a tool for the Dispatcher / MCP
1. Create `gateway/app/tools/<name>.py` with a Pydantic args model, a handler, and a `Tool(name, tier, scopes)` registration.
2. Pick the tier: T0 read, T1 reversible write, T2 irreversible. T2 requires a maintainer review.
3. Add a unit test and an agent scenario in `eval/agent_scenarios/` that needs the tool.
4. Update the tool tables in `docs/AGENTS.md` and `docs/MCP.md`, and `AI_USAGE_DISCLOSURE.md`.

## Adding a Demo Mode scenario
Add `demo/scenarios/<name>.yaml` (nodes, links, scheduled events) and a determinism test.

## Adding a new model
- Add to `models.lock` (name, license, size, checksum), benchmark on the Lite profile, and document RAM/latency. Confirm that it supports tool-calling if it will be used by the Dispatcher.

## Adding a transport (e.g., LoRa)
Implement `Transport` (`send`, `on_packet`, `mtu`) in mobile or the bridge; the RMP codec stays unchanged. Add a matching `SimTransport` profile in `demo/transport.py`.

## Issue labels
`frogtoberfest`, `good first issue`, `help wanted`, `area:mesh`, `area:ai`, `area:agent`, `area:mobile`, `area:dashboard`, `area:demo`, `area:docs`, `i18n`, `a11y`.

## Starter issues
- Nepali keyword lists for the fallback extractor
- Dashboard dark mode
- Add H3 heatmap layer
- Mesh simulator: visualize hop paths
- Write eval cases for flood messages
- Battery-aware scan duty cycle
- Tile pack downloader CLI
- Translate UI strings (Newari, Maithili, Tamang)
- Demo scenario: landslide on a highway
- Agent scenario set for flood cases (NE text)
- Mesh Lab: packet hop trail animation
- Tool: `get_weather_cached` (offline snapshot)

## PR checklist
- [ ] Tests added/updated
- [ ] Docs updated
- [ ] AI fallback exists (if AI feature)
- [ ] No new network/telemetry
- [ ] AI Usage Disclosure updated (if AI-related)
- [ ] New tools have a tier, a test, and an agent scenario
- [ ] If AI-assisted code was used, disclosed in the PR description
