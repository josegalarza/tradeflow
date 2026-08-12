"""Slack notifications, with graceful degradation.

Two rules shape this module.

*It must never be the reason a pipeline fails.* A notifier that raises when Slack
is unreachable turns a successful build into a failed one, and turns a failed
build into a failure with a misleading cause. Every send is wrapped, and a
delivery failure is logged rather than propagated.

*It must work with no configuration at all.* Somebody cloning this repo has no
webhook, and the run should still show them what a notification would have said.
With ``SLACK_WEBHOOK_URL`` unset the payload is rendered to stdout instead, which
also makes the formatting testable without a network.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

WEBHOOK_ENV_VAR = "SLACK_WEBHOOK_URL"
REQUEST_TIMEOUT_SECONDS = 10


@dataclass
class RunSummary:
    """What a dbt invocation did, in the shape a human wants to read."""

    target: str = "dev"
    models_built: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_warned: int = 0
    elapsed_seconds: float = 0.0
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.tests_failed == 0

    @classmethod
    def from_run_results(cls, path: Path) -> RunSummary:
        """Parse dbt's own ``run_results.json``.

        dbt already writes a complete, structured account of the run. Producing a
        second one from log scraping would be a worse copy of a file that is
        guaranteed to be accurate.
        """
        with path.open() as handle:
            payload = json.load(handle)

        summary = cls(
            target=payload.get("args", {}).get("target", "dev"),
            elapsed_seconds=round(payload.get("elapsed_time", 0.0), 1),
        )

        for result in payload.get("results", []):
            unique_id = result.get("unique_id", "")
            status = result.get("status")
            if unique_id.startswith("model."):
                if status == "success":
                    summary.models_built += 1
            elif unique_id.startswith("test."):
                name = unique_id.split(".")[-2] if "." in unique_id else unique_id
                if status == "pass":
                    summary.tests_passed += 1
                elif status == "warn":
                    summary.tests_warned += 1
                    summary.warnings.append(name)
                elif status in ("fail", "error"):
                    summary.tests_failed += 1
                    summary.failures.append(name)

        return summary


def _blocks_for(summary: RunSummary) -> list[dict[str, Any]]:
    icon = ":white_check_mark:" if summary.ok else ":rotating_light:"
    headline = "build passed" if summary.ok else "build FAILED"

    fields = [
        f"*Target*\n`{summary.target}`",
        f"*Duration*\n{summary.elapsed_seconds}s",
        f"*Models*\n{summary.models_built}",
        f"*Tests*\n{summary.tests_passed} passed / "
        f"{summary.tests_warned} warned / {summary.tests_failed} failed",
    ]

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{icon} tradeflow {headline}"},
        },
        {
            "type": "section",
            "fields": [{"type": "mrkdwn", "text": text} for text in fields],
        },
    ]

    # Failures first and capped. A Slack message listing 200 failed tests is
    # scrolled past; the first few plus a count is read.
    if summary.failures:
        listed = "\n".join(f"• `{name}`" for name in summary.failures[:8])
        extra = (
            f"\n… and {len(summary.failures) - 8} more"
            if len(summary.failures) > 8
            else ""
        )
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Failed tests*\n{listed}{extra}",
                },
            }
        )

    if summary.warnings:
        listed = "\n".join(f"• `{name}`" for name in summary.warnings[:5])
        extra = (
            f"\n… and {len(summary.warnings) - 5} more"
            if len(summary.warnings) > 5
            else ""
        )
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Warnings* (detectors -- defects quarantined, "
                        f"pipeline continued)\n{listed}{extra}"
                    ),
                },
            }
        )

    if summary.row_counts:
        rows = "\n".join(
            f"• `{name}`: {count:,}"
            for name, count in sorted(summary.row_counts.items(), key=lambda kv: -kv[1])[
                :6
            ]
        )
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Rows*\n{rows}"}}
        )

    return blocks


def send(summary: RunSummary, webhook_url: str | None = None) -> bool:
    """Post the summary to Slack. Returns True if it was delivered.

    Never raises. A monitoring channel that can take down the thing it monitors
    is a liability.
    """
    payload = {"blocks": _blocks_for(summary)}
    url = webhook_url or os.environ.get(WEBHOOK_ENV_VAR)

    if not url:
        logger.info(
            "%s not set -- printing the notification instead of sending it",
            WEBHOOK_ENV_VAR,
        )
        print(render_text(summary))
        return False

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            if 200 <= response.status < 300:
                return True
            logger.warning("Slack responded %s", response.status)
            return False
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        # Deliberately swallowed. See the module docstring.
        logger.warning("could not deliver Slack notification: %s", error)
        return False


def render_text(summary: RunSummary) -> str:
    """Plain-text rendering, for stdout and for tests."""
    status = "PASSED" if summary.ok else "FAILED"
    lines = [
        "",
        "+" + "-" * 62 + "+",
        f"| tradeflow build {status:<45}|",
        "+" + "-" * 62 + "+",
        f"|  target      {summary.target:<48}|",
        f"|  duration    {str(summary.elapsed_seconds) + 's':<48}|",
        f"|  models      {summary.models_built:<48}|",
        f"|  tests       {f'{summary.tests_passed} passed, {summary.tests_warned} warned, {summary.tests_failed} failed':<48}|",
    ]
    if summary.failures:
        lines.append("|" + " " * 62 + "|")
        lines.append(f"|  failures:{'':<51}|")
        for name in summary.failures[:8]:
            lines.append(f"|    x {name[:54]:<56}|")
    if summary.warnings:
        lines.append("|" + " " * 62 + "|")
        lines.append(f"|  warnings (quarantined, pipeline continued):{'':<18}|")
        for name in summary.warnings[:5]:
            lines.append(f"|    ~ {name[:54]:<56}|")
    lines.append("+" + "-" * 62 + "+")
    if not os.environ.get(WEBHOOK_ENV_VAR):
        lines.append(f"  (set {WEBHOOK_ENV_VAR} to deliver this to Slack instead)")
    lines.append("")
    return "\n".join(lines)
