# Local AI brief evaluation

## Scope and reproducibility

This is a small, synthetic, manually annotated evaluation of **report-to-needs
parsing**, not a production benchmark or a safety certification. No runtime code
was modified for this evaluation.

Artifacts are in `backend\tests\ai_eval`:

- `cases.json`: 30 English/Romanized Nepali messages, including fragments, typos,
  missing locations/amounts, mixed needs, negation, completed incidents, offers,
  and messages containing no request.
- `evaluate.py`: executable evaluator using the real `ai.report_tasks.parse_report`
  wrapper and `rule_based_report`, not a replacement parser.
- `results.json`: measured predictions, per-case scores, source, timings, wrapper
  validation/error logs, model inventory/digests, corpus/prompt hashes, and totals.
- `long_timeout_results.json`: one additional live report with a longer timeout
  and a strict total deadline; retained separately rather than replacing results.
- `test_evaluate.py`: corpus/scoring checks and a real-wrapper outage test.

Run from `D:\Rahat final` with the existing virtual environment:

```powershell
# Recorded run: all 30 baseline + all 30 simulated-outage + first five live cases.
& '.\.venv\Scripts\python.exe' -m backend.tests.ai_eval.evaluate --mode all --max-cases 5 --timeout 35 --budget-seconds 480

# Recorded follow-up: one first-case retry with a longer per-attempt allowance.
& '.\.venv\Scripts\python.exe' -m backend.tests.ai_eval.evaluate --mode model --max-cases 1 --timeout 90 --budget-seconds 100 --output backend\tests\ai_eval\long_timeout_results.json

# The path entry point also works from the repository root.
& '.\.venv\Scripts\python.exe' backend\tests\ai_eval\evaluate.py --mode baseline --output backend\tests\ai_eval\baseline_results.json

# Request every live case, still bounded by the total wall-clock budget.
& '.\.venv\Scripts\python.exe' -m backend.tests.ai_eval.evaluate --mode all --max-cases 30 --timeout 90 --budget-seconds 600 --output backend\tests\ai_eval\full_results.json

# Optional comparison ONLY if this model is already installed.
& '.\.venv\Scripts\python.exe' -m backend.tests.ai_eval.evaluate --mode model --model qwen2.5:7b --max-cases 5 --timeout 90 --budget-seconds 600 --output backend\tests\ai_eval\seven_b_results.json

& '.\.venv\Scripts\python.exe' -m pytest backend\tests\ai_eval\test_evaluate.py -q -p no:cacheprovider
```

No packages or models are installed by the script. Live mode checks
`http://127.0.0.1:11434/api/tags` and refuses an absent model; all inference uses
that local address. Both `qwen2.5:3b` (Q4_K_M, approximately 1.93 GB model file)
and `qwen2.5:7b` (Q4_K_M, approximately 4.68 GB) were present. The 3B model is the
default for this 8 GB laptop. These are file sizes, **not** measured RAM usage.
The 7B model was not benchmarked; no relative speed/accuracy claim is made.

Run only one live evaluation/integration inference process at a time. Calls
within this evaluator are sequential; it does not install a global semaphore
for other application processes. The existing Ollama service is reused; no
background server is started.

## Isolation and method

The evaluator explicitly creates `sqlite:///:memory:` and seeds only ten
controlled skill names, listed in the JSON, plus a short fixed location list.
These are evaluation fixtures, not a copy of a deployment's database.
`parse_report` receives this in-memory SQLAlchemy session. Its `AICallLog` rows
are flushed, copied into the evaluation JSON, then rolled back after each case.
The only seed commit is against this in-memory engine. No application endpoint,
real report table, real database, or external API is used.

Three modes keep quality and reliability separate:

1. **baseline** validates the keyword parser output against `ParsedReport`.
2. **offline** deliberately replaces the Ollama generate method with a local
   `ConnectionError`. The real wrapper performs both retries and its real
   schema-validated fallback. This measures fallback plumbing, not a real
   network outage's duration.
3. **model** invokes the real wrapper against installed Ollama. The wrapper may
   retry once. `source=ai` means a model response passed schema and controlled
   skill validation; `source=fallback` means the keyword result, not AI success.
   An outer deadline bounds each case and the live phase. Cancellation can
   produce an error without completed wrapper logs; such rows remain failures.

`--timeout` is per attempt, not per report. The outer live limit is the smaller
of the remaining budget and `2 * timeout + 5` seconds. The budget starts before
the baseline/offline loops; it prevents further live calls when exhausted.
The inventory request/import/setup time is outside that measured budget.
Results are checkpointed after every completed/failed case. Output paths must
remain under `backend\tests\ai_eval`.

## Labels and metrics

- Categories are **sets**, so order and duplicate mentions do not affect exact
  match. Extra categories are errors. Distinct requested needs are labeled;
  past/resolved needs, donations, and schedule questions are not new requests.
  A vague assistance request or transport request is `other`. Six cases have
  an empty expected category set.
- Category exact accuracy is correct completed reports / completed reports.
  Attempted, completed, failed, and source counts are also reported; failures
  are not silently converted into accurate predictions. Empty denominators
  produce JSON `null`, never invented percentages.
- Micro precision/recall/F1 aggregate category-set TP/FP/FN. A correct empty
  set improves exact accuracy but adds no category true positive.
- Only three unequivocal trapped/rescue cases carry an urgency label (5).
  Six explicit English-unit family counts are checked. This is not broad
  urgency calibration or Nepali number-word extraction coverage.
- Fourteen category-specific quantity/unit checks include explicit amounts
  and explicit unknowns. Unknown amounts must remain null. Family counts and
  people needing rescue must not become supply quantities. Unit comparison is
  case-insensitive but otherwise exact; equivalent unit spellings/conversions
  are not normalized. Both missing and extra matching-category needs fail the
  corresponding quantity check.
- Latency uses `perf_counter` around parsing/schema validation and, for the
  wrapper, its attempts/retries. It excludes copying logs, database flushing,
  and result-file writing. Mean, median, maximum, and total are saved.
  First-call loading and laptop contention are not controlled.

## Recorded results: 2026-10-25

Measured baseline and simulated outage (all 30 cases):

| Mode | Source | Completed / attempted | Exact category sets | Micro F1 | Mean latency | Median | Maximum |
|---|---|---:|---:|---:|---:|---:|---:|
| Keyword | `keyword` | 30 / 30 | 20 / 30 (66.67%) | 0.8125 | 0.351 ms | 0.273 ms | 2.465 ms |
| Simulated outage | `fallback` | 30 / 30 | 20 / 30 (66.67%) | 0.8125 | 582.218 ms | 543.337 ms | 839.959 ms |

Both modes scored urgency **3/3**, family count **6/6**, and quantities **10/14**.
Neither had a report-level exception. The outage run recorded **60 failed
attempts**, followed by **30 valid fallback records**. There were no
`source=ai` results in this deliberately offline run.

Live Ollama was actually invoked for the **first five cases**, in corpus order:
`en-water`, `ne-food`, `en-rescue`, `ne-medical`, `en-no-request`. This is
**5/30 coverage, not a full model benchmark**.

| Mode on the same five cases | Sources | Exact category sets | Micro F1 | Mean latency | Median | Maximum |
|---|---|---:|---:|---:|---:|---:|
| Matched keyword subset | 5 `keyword` | 3 / 5 (60%) | 0.7273 | 0.722 ms | 0.306 ms | 2.465 ms |
| Live 3B wrapper, 35 s/attempt | 5 `fallback`, **0 `ai`** | 3 / 5 (60%) | 0.7273 | 72,339.912 ms | 72,299.565 ms | 72,961.724 ms |

All **10 actual model attempts timed out** (`ReadTimeout`). All five reports
returned schema-valid fallback, so report-level exceptions were zero, but the
validated model-response success rate was **0/5**. AI-only semantic accuracy is
**unavailable**, not 60%. `model_ai_only` correctly has zero cases and null
accuracy. Urgency was 1/1, family count 2/2, and quantity 4/4 on this subset,
all from fallback.

Programmatic equality checking confirmed that all five complete parsed fallback
objects exactly matched their keyword counterparts. Thus the observed end-to-end
category-accuracy change was **0 percentage points** on matched cases, with
roughly **72.34 seconds added per report**. This does **not** establish whether a
successfully completed model response would improve semantic accuracy.
The complete baseline/outage/five-case run took **380.663 seconds** inside the
evaluator's timed phase. Running 30 live cases was not feasible in the short
evaluation budget at the observed timeout behavior. No model download or
parallel inference was attempted.

### Longer-timeout follow-up

After the five-case run had finished, `en-water` alone was attempted again with
**90 seconds per attempt and a 100-second total budget**. It still did not
produce a completed wrapper result before the outer deadline:

- attempted reports: **1**; completed: **0**; report failures: **1**;
- source: **`error`**, `TimeoutError`, not fallback or AI;
- observed per-report latency: **100,033.384 ms**;
- total timed run: **100.924 seconds**;
- accuracy: **unavailable/null** (no parsed output).

The cancellation occurred before the wrapper persisted its accumulated attempt
logs, so this artifact has an empty `wrapper_logs` list. Its zero
`wrapper_failed_attempts` count means **zero captured attempt logs**, not proof
that no model attempt failed. The wrapper's source/accuracy must not be inferred
from an aborted call. Corpus and prompt hashes match the main run.
This extra trial repeats one of the same five cases; it does not increase
distinct live coverage beyond 5/30. There were **no validated `source=ai`
responses in either measured live run**. A 90-second attempt limit alone does
not guarantee a report completes within 100 seconds when retries are enabled.

### Verification

The focused evaluator suite passed: **5 tests**. Pylance reported no syntax
errors in either Python implementation/test file. Both the module command and
the direct script path were executed; the direct path completed all 30 baseline
cases. The disposable path-smoke/test result files were removed.

## Error analysis and interpretation

Keyword mismatches are visible in `results.json`:

- `en-rescue` treats rising flood water as a drinking-water request.
- `en-no-request`, `en-negation`, `en-offer`, `en-resolved`, and `en-question`
  ignore context/negation and invent actionable needs from mentioned keywords.
- `ne-repair` mistakes Romanized Nepali **pani** ("also" in this sentence) for
  a drinking-water request.
- `en-vague` and `en-transport` fail to create the expected `other` need;
  `en-typos` misses misspelled drinking water.
- Quantity failures are `en-medical-count`, `en-shelter-count`, and both
  per-category quantities in `en-separated-quantity`. The keyword quantity
  expression requires adjacent number/unit text and only assigns an amount
  when exactly one need is found.

These are observed limitations, not changes to runtime behavior. A successful
schema validation is **not** a claim that the semantics are correct. Even a
small-model improvement on five cases cannot establish performance across all
30, real incoming reports, or all Romanized Nepali variants. This hand-authored
set has no independent adjudication, held-out training guarantee, statistical
power, or production representativeness. Locations, vulnerability extraction,
hazards, follow-up quality, skill correctness beyond the allow-list, and
downstream dispatch outcomes are not scored.

Use source indicators and coordinator review in demonstrations. Do not describe
fallback output as model inference, extrapolate a partial live run to 30 cases,
or use these measurements to authorize unattended emergency decisions.
