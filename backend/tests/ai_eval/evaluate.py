"""Run from the repository root; no real database, external API, or model pulls."""

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SKILLS = [
    "doctor", "nurse", "first_aid", "search_and_rescue", "boat_operator",
    "driver", "electrician", "plumber", "logistics", "cooking",
]
LOCATIONS = ["Melamchi", "Sindhupalchowk", "Chautara", "Ward 3"]


def load_cases():
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    if len(cases) != 30 or len({case["id"] for case in cases}) != 30:
        raise ValueError("Expected exactly 30 distinct cases")
    return cases


def score(case, parsed):
    expected = set(case["categories"])
    actual = {need["category"] for need in parsed["needs"]}
    result = {
        "category_exact": actual == expected,
        "true_positive": len(expected & actual),
        "false_positive": len(actual - expected),
        "false_negative": len(expected - actual),
    }
    for field in ("urgency", "families_affected"):
        if field in case:
            result[field + "_correct"] = parsed[field] == case[field]
    quantity_checks = []
    for category, (quantity, unit) in case.get("quantities", {}).items():
        needs = [need for need in parsed["needs"] if need["category"] == category]
        quantity_checks.append(
            len(needs) == 1
            and needs[0]["quantity"] == quantity
            and (needs[0]["unit"] or "").casefold() == (unit or "").casefold()
        )
    result["quantity_checks"] = quantity_checks
    return result


def summarize(rows):
    completed = [row for row in rows if row["status"] == "completed"]
    scores = [row["score"] for row in completed]
    tp = sum(s["true_positive"] for s in scores)
    fp = sum(s["false_positive"] for s in scores)
    fn = sum(s["false_negative"] for s in scores)
    exact = sum(s["category_exact"] for s in scores)
    latencies = sorted(row["latency_ms"] for row in rows)
    result = {
        "attempted": len(rows), "completed": len(completed),
        "failures": len(rows) - len(completed),
        "source_counts": dict(Counter(row["source"] for row in rows)),
        "category_exact_correct": exact,
        "category_exact_accuracy": exact / len(completed) if completed else None,
        "micro_precision": tp / (tp + fp) if tp + fp else None,
        "micro_recall": tp / (tp + fn) if tp + fn else None,
        "micro_f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        "latency_ms_total": round(sum(latencies), 3),
        "latency_ms_mean": round(statistics.mean(latencies), 3) if latencies else None,
        "latency_ms_p50": round(statistics.median(latencies), 3) if latencies else None,
        "latency_ms_max": max(latencies) if latencies else None,
        "wrapper_failed_attempts": sum(
            log["validation_result"] not in ("valid", "fallback_valid")
            for row in rows for log in row.get("wrapper_logs", [])
        ),
    }
    for metric in ("urgency", "families_affected", "quantity"):
        checks = (
            [check for s in scores for check in s["quantity_checks"]]
            if metric == "quantity" else
            [s[metric + "_correct"] for s in scores if metric + "_correct" in s]
        )
        result[metric] = {
            "correct": sum(checks), "scored": len(checks),
            "accuracy": sum(checks) / len(checks) if checks else None,
        }
    return result


async def run(args):
    # Set before importing app.db; the separate evaluation engine is also memory-only.
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "backend"))
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from app.db import Base
    from app.models import AICallLog, Skill
    import ai.client as client
    import ai.report_tasks as reports
    from ai.schemas import ParsedReport

    cases = load_cases()
    modes = ["baseline", "offline", "model"] if args.mode == "all" else [args.mode]
    inventory = []
    if "model" in modes:
        # This read-only endpoint never pulls or downloads models.
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as response:
            inventory = json.load(response)["models"]
        if args.model not in {model["name"] for model in inventory}:
            raise ValueError(f"Model {args.model!r} is not installed; no download attempted")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    rows = []
    started = time.perf_counter()
    result = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model, "ollama_url": "http://127.0.0.1:11434",
        "installed_models": inventory, "prompt_version": reports.REPORT_PROMPT_VERSION,
        "corpus_sha256": hashlib.sha256((HERE / "cases.json").read_bytes()).hexdigest(),
        "prompt_sha256": hashlib.sha256(
            (reports.PROMPT_DIR / f"{reports.REPORT_PROMPT_VERSION}.txt").read_bytes()
        ).hexdigest(),
        "timeout_seconds_per_attempt": args.timeout, "max_model_cases": args.max_cases,
        "budget_seconds": args.budget_seconds, "skills": SKILLS, "locations": LOCATIONS,
        "database": "sqlite:///:memory:", "rows": rows,
    }
    output = Path(args.output).resolve()
    if not output.is_relative_to(HERE):
        raise ValueError("Evaluation output must stay inside backend/tests/ai_eval")
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        result["summary"] = {mode: summarize([r for r in rows if r["mode"] == mode]) for mode in modes}
        result["model_ai_only"] = summarize([r for r in rows if r["mode"] == "model" and r["source"] == "ai"])
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    async def unavailable(*unused_args, **unused_kwargs):
        raise ConnectionError("Intentional local evaluation outage; no network request")

    try:
        with Session(engine) as db:
            db.add_all(Skill(name=name, category="evaluation") for name in SKILLS)
            db.commit()  # Only the explicitly created in-memory engine.
            with patch.object(client, "OLLAMA_MODEL", args.model), patch.object(
                client, "OLLAMA_URL", "http://127.0.0.1:11434"
            ), patch.object(reports, "REPORT_AI_TIMEOUT_SECONDS", args.timeout):
                for mode in modes:
                    selected = cases[:args.max_cases] if mode == "model" else cases
                    for case in selected:
                        remaining = args.budget_seconds - (time.perf_counter() - started)
                        if mode == "model" and remaining <= 0:
                            result["stop_reason"] = "model wall-clock budget exhausted"
                            break
                        tick = time.perf_counter()
                        row = {"id": case["id"], "mode": mode, "source": "error", "status": "failed"}
                        try:
                            if mode == "baseline":
                                parsed = ParsedReport.model_validate(reports.rule_based_report(case["text"], SKILLS, LOCATIONS))
                                source = "keyword"
                            else:
                                context = patch.object(client.ollama.AsyncClient, "generate", unavailable) if mode == "offline" else patch.dict(os.environ, {})
                                with context:
                                    parsed, source = await asyncio.wait_for(
                                        reports.parse_report(db, case["text"], LOCATIONS),
                                        timeout=min(2 * args.timeout + 5, remaining) if mode == "model" else 5,
                                    )
                            row.update(status="completed", source=source, parsed=parsed.model_dump())
                            row["score"] = score(case, row["parsed"])
                        except Exception as exc:
                            row["error"] = f"{type(exc).__name__}: {exc}"
                        row["latency_ms"] = round((time.perf_counter() - tick) * 1000, 3)
                        db.flush()
                        row["wrapper_logs"] = [
                            {"model": log.model, "latency_ms": log.latency_ms,
                             "validation_result": log.validation_result,
                             "fallback_used": log.fallback_used, "output": log.output}
                            for log in db.scalars(select(AICallLog).order_by(AICallLog.id))
                        ]
                        rows.append(row)
                        db.rollback()  # Discard local wrapper logs after copying them.
                        save()
                        print(f"{mode} {case['id']}: {row['source']} {row['latency_ms']}ms", flush=True)
        save()
    finally:
        engine.dispose()
    print(json.dumps(result["summary"], indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["all", "baseline", "offline", "model"], default="all")
    parser.add_argument("--model", choices=["qwen2.5:3b", "qwen2.5:7b"], default="qwen2.5:3b")
    parser.add_argument("--max-cases", type=int, default=5, help="Model cases only; baseline/offline always run all 30")
    parser.add_argument("--timeout", type=float, default=30, help="Seconds per wrapper attempt (up to two attempts)")
    parser.add_argument("--budget-seconds", type=float, default=480)
    parser.add_argument("--output", default=str(HERE / "results.json"))
    args = parser.parse_args()
    if not 1 <= args.max_cases <= 30 or args.timeout <= 0 or args.budget_seconds <= 0:
        parser.error("max-cases must be 1..30; timeout and budget must be positive")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
