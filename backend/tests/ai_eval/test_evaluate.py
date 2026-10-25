import asyncio
import json
from argparse import Namespace
from pathlib import Path

from backend.tests.ai_eval.evaluate import load_cases, run, score, summarize


def test_corpus_and_exact_set_scoring():
    cases = load_cases()
    assert len(cases) == 30
    assert {c["language"] for c in cases} == {"en", "romanized_nepali"}
    assert sum(not c["categories"] for c in cases) == 6
    parsed = {"needs": [{"category": "water", "quantity": 200, "unit": "litres"}], "families_affected": 12}
    scores = score(cases[0], parsed)
    assert scores["category_exact"]
    assert scores["quantity_checks"] == [True]
    assert scores["families_affected_correct"]
    parsed["needs"].append({"category": "food"})
    assert not score(cases[0], parsed)["category_exact"]


def test_empty_summary_has_no_fabricated_accuracy():
    summary = summarize([])
    assert summary["category_exact_accuracy"] is None
    assert summary["latency_ms_mean"] is None


def test_unknown_quantities_and_empty_requests_are_not_invented():
    case = {"categories": ["food"], "quantities": {"food": [None, None]}}
    parsed = {"needs": [{"category": "food", "quantity": None, "unit": None}]}
    assert score(case, parsed)["quantity_checks"] == [True]
    parsed["needs"][0]["quantity"] = 30
    assert score(case, parsed)["quantity_checks"] == [False]
    assert not score({"categories": []}, parsed)["category_exact"]
    assert score({"categories": []}, {"needs": []})["category_exact"]


def test_report_failures_are_counted_separately():
    summary = summarize([
        {"status": "failed", "source": "error", "latency_ms": 100, "wrapper_logs": []},
    ])
    assert summary["attempted"] == 1
    assert summary["failures"] == 1
    assert summary["completed"] == 0
    assert summary["source_counts"] == {"error": 1}
    assert summary["category_exact_accuracy"] is None


def test_real_wrapper_fallback_is_isolated(monkeypatch):
    # run() writes only inside its own directory; remove this test artifact afterward.
    output = Path(__file__).with_name("test_results.json")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    try:
        result = asyncio.run(run(Namespace(
            mode="offline", model="qwen2.5:3b", max_cases=5,
            timeout=1, budget_seconds=30, output=str(output),
        )))
        assert result["summary"]["offline"]["completed"] == 30
        assert result["summary"]["offline"]["source_counts"] == {"fallback": 30}
        assert result["summary"]["offline"]["wrapper_failed_attempts"] == 60
        assert all(len(row["wrapper_logs"]) == 3 for row in result["rows"])
        assert json.loads(output.read_text(encoding="utf-8"))["database"] == "sqlite:///:memory:"
    finally:
        output.unlink(missing_ok=True)
