# Local Setup

These instructions are for the current Windows build: one FastAPI backend,
the public Flutter app, and the Flutter Service Station. They do not use the
legacy gateway, GraphHopper, Node, Docker or old `make` targets.

## Prerequisites

| Tool | Requirement |
|---|---|
| Python | 3.11 or later |
| Flutter | 3.24 or later, with a compatible Dart SDK |
| Ollama | Windows installation from https://ollama.com/download/windows |
| Browser | A current browser for the public app and station |
| Android tools | Only needed for an Android build or physical-device tests |

Download dependencies and the model before attempting an offline demonstration.
An 8 GB laptop can be memory-constrained; local inference latency must be
measured, not assumed.

## 1. Install the Backend

Open PowerShell at the repository root. The example path is this workspace;
use your checkout directory on another machine.

```powershell
Set-Location 'D:\Rahat final'
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Set-Location backend
..\.venv\Scripts\python.exe -m app.setup_local --demo
```

`app.setup_local` applies migrations and initializes local configuration and
reference records. `--demo` adds synthetic demonstration data. Do not run demo
seeding against a real response deployment, and do not delete a database to
work around a migration error.

The configuration reference is [../backend/.env.example](../backend/.env.example).
Keep secrets in the local environment, never in the public repository.

## 2. Prepare Ollama

After installing Ollama:

```powershell
ollama pull qwen2.5:3b
ollama list
```

The Windows installation normally runs a local service. Start `ollama serve`
in a separate terminal only if that service is not running. Do not launch a
second instance on port `11434`.

The backend reads these settings from its local environment:

```dotenv
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
```

The default model is a configuration choice, not proof of a completed model
comparison. Do not use a cloud tag for the documented local/offline setup.
The current code has no embedding model, `AGENT_MODE` or `AUTO_DISPATCH` setting.

Task timeout settings are defined in
[../backend/app/config.py](../backend/app/config.py). The wrapper can make two
attempts, so a request may take longer than one per-attempt timeout. First
model loading can add delay. See [AI_EVALUATION.md](AI_EVALUATION.md) before
promising interactive inference on this laptop.

## 3. Start the Backend

From the backend directory:

```powershell
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Keep this terminal open. Check http://127.0.0.1:8000/api/health and open
http://127.0.0.1:8000/docs for the API explorer. `/health` is not the backend
health route and returns 404. AI status is at http://127.0.0.1:8000/ai/status.

## 4. Start the Public App

In another terminal:

```powershell
Set-Location 'D:\Rahat final\frontend'
flutter pub get
flutter run -d web-server --web-hostname 127.0.0.1 --web-port 52394
```

Open http://127.0.0.1:52394. The browser build does not prove native BLE relay.
For Android build instructions, see [ANDROID_BLE.md](ANDROID_BLE.md).

## 5. Start the Service Station

In a third terminal:

```powershell
Set-Location 'D:\Rahat final\station'
flutter pub get
flutter run -d web-server --web-hostname 127.0.0.1 --web-port 52396
```

Open http://127.0.0.1:52396. The station and public app both use the same
backend on port `8000`; the station is not a second server-side datastore.

For the command station demo login, use `admin@demo.rahat.org` with password
`Rahat123!`. The demo also creates `coordinator@demo.rahat.org` and
`volunteer@demo.rahat.org`, both using password `RahatDemo2026!`. These are
public demonstration credentials, never deployment credentials.

## 6. Run Tests and Evaluation

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
.\.venv\Scripts\python.exe -m pytest backend\tests\ai_eval\test_evaluate.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m backend.tests.ai_eval.evaluate --mode baseline --output backend\tests\ai_eval\baseline_results.json
```

To attempt a bounded live comparison with the installed local model:

```powershell
.\.venv\Scripts\python.exe -m backend.tests.ai_eval.evaluate --mode all --max-cases 30 --timeout 90 --budget-seconds 600 --output backend\tests\ai_eval\full_results.json
```

This may finish fewer than thirty live cases. Inspect `source` and coverage;
do not count fallback as model success. Run one live evaluation at a time.

In each Flutter project, run `flutter analyze` and `flutter test`. These check
client code, not real GPS, radio delivery or model quality.

## Troubleshooting

| Symptom | What to Check |
|---|---|
| `/health` returns 404 | Use `/api/health`; check `/docs` for registered endpoints |
| Flutter reports `10048` | The port is occupied. Inspect its current owner and use the existing server or choose a free port |
| `Stop-Process` cannot find the PID | That process exited or the PID was stale. Query the listener again; do not reuse an old number |
| AI result says `fallback` | Inspect Ollama availability, installed model and `AICallLog`; timeout/rule output is not live AI evidence |
| SOS exists but has no need | Linking needs usable incident/location context; missing GPS is not replaced with invented coordinates |
| Weather data unavailable offline | A matching saved snapshot must already exist for those coordinates |
| A phone cannot reach the backend | `127.0.0.1` means the phone itself. Use a trusted LAN binding and a developer-controlled `BACKEND_BASE_URL` build value |

To inspect occupied ports:

```powershell
Get-NetTCPConnection -LocalPort 8000,52394,52396 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, OwningProcess
```

Use the existing page when it belongs to this project. If a separate instance
is needed, choose a free port, for example `--web-port 52397`. Stop only a
process you have identified and intend to stop; do not kill every Dart process.

Before recording, follow [DEMO.md](DEMO.md) and review
[LIMITATIONS.md](LIMITATIONS.md). No setup command certifies a production
emergency deployment.
