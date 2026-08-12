"""Tests for the Slack notifier.

The behaviour that matters most is what happens when Slack is *not* reachable:
the notifier must never be the reason a pipeline fails. So most of these assert
that failure paths return False rather than raise.
"""

from __future__ import annotations

import json

from orchestration.notifications import RunSummary, render_text, send


def write_run_results(path, results):
    path.write_text(
        json.dumps(
            {
                "args": {"target": "ci"},
                "elapsed_time": 12.34,
                "results": results,
            }
        )
    )
    return path


def test_summary_parses_dbt_run_results(tmp_path):
    path = write_run_results(
        tmp_path / "run_results.json",
        [
            {"unique_id": "model.tradeflow.fct_orders", "status": "success"},
            {"unique_id": "model.tradeflow.dim_customer", "status": "success"},
            {"unique_id": "test.tradeflow.unique_a.1", "status": "pass"},
            {"unique_id": "test.tradeflow.not_null_b.2", "status": "fail"},
            {"unique_id": "test.tradeflow.relationships_c.3", "status": "warn"},
        ],
    )
    summary = RunSummary.from_run_results(path)

    assert summary.target == "ci"
    assert summary.models_built == 2
    assert summary.tests_passed == 1
    assert summary.tests_failed == 1
    assert summary.tests_warned == 1
    assert summary.elapsed_seconds == 12.3
    assert not summary.ok


def test_clean_run_is_ok(tmp_path):
    path = write_run_results(
        tmp_path / "run_results.json",
        [{"unique_id": "test.tradeflow.unique_a.1", "status": "pass"}],
    )
    assert RunSummary.from_run_results(path).ok


def test_warnings_alone_do_not_fail_the_summary(tmp_path):
    """Detectors warn; only the gate fails. The summary has to reflect that."""
    path = write_run_results(
        tmp_path / "run_results.json",
        [{"unique_id": "test.tradeflow.detector.1", "status": "warn"}],
    )
    summary = RunSummary.from_run_results(path)
    assert summary.ok
    assert summary.tests_warned == 1


def test_send_without_a_webhook_degrades_instead_of_raising(monkeypatch, capsys):
    """A stranger cloning the repo has no webhook and the run must still work."""
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    delivered = send(RunSummary(models_built=3, tests_passed=10))
    assert delivered is False
    printed = capsys.readouterr().out
    assert "tradeflow build PASSED" in printed
    assert "SLACK_WEBHOOK_URL" in printed


def test_send_swallows_transport_errors(monkeypatch):
    """A monitoring channel must not be able to take down what it monitors."""
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "http://127.0.0.1:9/definitely-not-listening")
    assert send(RunSummary(tests_failed=1, failures=["some_test"])) is False


def test_rendered_text_lists_failures_and_warnings():
    summary = RunSummary(
        models_built=26,
        tests_passed=300,
        tests_failed=1,
        tests_warned=2,
        failures=["assert_reject_rate_within_threshold"],
        warnings=["unique_stg_executions_execution_id", "not_null_email"],
    )
    text = render_text(summary)
    assert "FAILED" in text
    assert "assert_reject_rate_within_threshold" in text
    assert "quarantined, pipeline continued" in text


def test_long_failure_lists_are_truncated():
    """A message listing 200 failures is scrolled past, not read."""
    from orchestration.notifications import _blocks_for

    summary = RunSummary(tests_failed=40, failures=[f"test_{i}" for i in range(40)])
    blocks = _blocks_for(summary)
    failure_block = next(
        block
        for block in blocks
        if block.get("type") == "section"
        and "Failed tests" in block.get("text", {}).get("text", "")
    )
    assert "and 32 more" in failure_block["text"]["text"]
