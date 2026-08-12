#!/usr/bin/env python
"""CI gate: every column that needs a classification has one.

This is the script that makes the governance framework real rather than
decorative. Tags that are merely *encouraged* decay -- someone adds a column
during a busy week, nobody notices, and six months later the masking policy has
a hole in it that nobody can date. A gate in CI means an untagged column cannot
merge, so the framework's coverage can only go up.

Three checks, in increasing order of how much they have caught:

1. **Coverage.** Every column in the layers listed in policy.yml, plus every
   column of any model marked ``contains_pii``, carries an explicit
   classification.
2. **Under-classification.** A column whose *name* looks like personal data
   (``email``, ``ip_address``, ``date_of_birth``, ...) but is classified below
   ``confidential``. This catches the specific failure of tagging a sensitive
   column ``internal`` to get past check 1.
3. **Coherence.** A column marked ``pii: true`` above the role clearances must
   declare a masking strategy, and every declared strategy must exist.

Exit code 0 if the warehouse is compliant, 1 if not. Prints a coverage summary
either way, which is what gets pasted into the CI job summary.

Usage::

    python -m governance.check_classification
    python -m governance.check_classification --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from governance.policy import (
    Column,
    Model,
    Policy,
    PolicyError,
    load_models,
)


@dataclass
class Finding:
    severity: str  # "error" | "warning"
    check: str
    model: str
    column: str
    message: str


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    total_columns: int = 0
    explicit_columns: int = 0
    technical_columns: int = 0
    inherited_columns: int = 0
    pii_columns: int = 0
    undocumented_columns: int = 0
    exemptions: int = 0
    required_columns: int = 0
    required_covered: int = 0
    coverage_by_layer: dict[str, tuple[int, int]] = field(default_factory=dict)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def info(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "info"]

    @property
    def coverage(self) -> float:
        """Share of columns the policy requires a tag for that have one."""
        if self.required_columns == 0:
            return 100.0
        return 100.0 * (self.required_covered / self.required_columns)


def requires_full_coverage(policy: Policy, model: Model) -> bool:
    enforcement = policy.enforcement
    if model.layer in enforcement.get("require_full_coverage_in_layers", []):
        return True
    return bool(
        enforcement.get("require_full_coverage_when_contains_pii") and model.contains_pii
    )


def looks_like_pii(policy: Policy, column: Column) -> bool:
    patterns = policy.enforcement.get("suspicious_column_patterns", [])
    name = column.name.lower()
    return any(pattern in name for pattern in patterns)


def check(policy: Policy, models: list[Model]) -> Report:
    report = Report()
    minimum = policy.enforcement["minimum_classification_for_pii"]
    minimum_rank = policy.rank(minimum)

    for model in models:
        needs_coverage = requires_full_coverage(policy, model)
        layer_total, layer_explicit = report.coverage_by_layer.get(model.layer, (0, 0))

        for column in model.columns:
            report.total_columns += 1
            layer_total += 1

            if column.is_technical:
                report.technical_columns += 1
            elif column.classification_source == "explicit":
                report.explicit_columns += 1
                layer_explicit += 1
            else:
                report.inherited_columns += 1

            # Coverage is measured against columns the policy actually requires a
            # tag for. Counting derived mart arithmetic in the denominator would
            # report a number that can never reach 100% and therefore tells
            # nobody anything.
            if needs_coverage and not column.is_technical:
                report.required_columns += 1
                if column.classification_source == "explicit":
                    report.required_covered += 1

            if column.is_pii:
                report.pii_columns += 1

            # --- check 0: undocumented column ----------------------------- #
            # An error only where the policy demands full coverage. Elsewhere it
            # is the layer default doing its job: derived arithmetic in the marts
            # inherits `internal`, exactly as policy.yml says it should, and
            # emitting a warning per SUM() column would bury the findings that
            # matter under noise nobody reads.
            if column.classification_source == "undocumented":
                report.undocumented_columns += 1
                if needs_coverage:
                    report.findings.append(
                        Finding(
                            severity="error",
                            check="undocumented_column",
                            model=model.name,
                            column=column.name,
                            message=(
                                "exists in the warehouse but appears in no schema "
                                "YAML, so nothing is known about its sensitivity. "
                                "This model requires full coverage because it is "
                                f"{'PII-bearing' if model.contains_pii else 'in ' + model.layer}."
                            ),
                        )
                    )

            # --- check 1: coverage ---------------------------------------- #
            elif (
                needs_coverage
                and not column.is_technical
                and column.classification_source != "explicit"
            ):
                report.findings.append(
                    Finding(
                        severity="error",
                        check="coverage",
                        model=model.name,
                        column=column.name,
                        message=(
                            "missing meta.classification. This model requires full "
                            f"coverage ({'PII-bearing' if model.contains_pii else model.layer}). "
                            "Add one of: "
                            f"{', '.join(sorted(policy.classifications))}."
                        ),
                    )
                )

            # --- check 0b: stale documentation ---------------------------- #
            if not column.in_database:
                report.findings.append(
                    Finding(
                        severity="warning",
                        check="documented_but_absent",
                        model=model.name,
                        column=column.name,
                        message=(
                            "documented in the schema YAML but not present in the "
                            "built warehouse. Either the model stopped selecting "
                            "it or the documentation was written ahead of the SQL. "
                            "Secure-view generation skips it."
                        ),
                    )
                )

            # --- check 2: under-classification ---------------------------- #
            if looks_like_pii(policy, column):
                if policy.rank(column.classification) < minimum_rank:
                    if column.rationale:
                        # A documented exemption. Recorded, surfaced in the
                        # catalog, and not a failure.
                        report.exemptions += 1
                        report.findings.append(
                            Finding(
                                severity="info",
                                check="documented_exemption",
                                model=model.name,
                                column=column.name,
                                message=(
                                    f"classified {column.classification!r}, below the "
                                    f"{minimum!r} minimum, with rationale: "
                                    f"{column.rationale}"
                                ),
                            )
                        )
                    else:
                        report.findings.append(
                            Finding(
                                severity="error",
                                check="under_classification",
                                model=model.name,
                                column=column.name,
                                message=(
                                    f"name suggests personal data but classification "
                                    f"is {column.classification!r}, below the required "
                                    f"minimum of {minimum!r}. Either raise the "
                                    "classification, or -- if this column is genuinely "
                                    "lower risk -- declare "
                                    "meta.classification_rationale explaining why. "
                                    "Exceptions are allowed; undocumented ones are "
                                    "not."
                                ),
                            )
                        )
                elif not column.is_pii:
                    report.findings.append(
                        Finding(
                            severity="warning",
                            check="missing_pii_flag",
                            model=model.name,
                            column=column.name,
                            message=(
                                "name suggests personal data but meta.pii is not "
                                "set. The classification is adequate; the flag is "
                                "what the catalog and the subject-access report "
                                "read."
                            ),
                        )
                    )

            # --- check 3: coherence --------------------------------------- #
            if column.masking is not None:
                if column.masking not in policy.masking_strategies:
                    report.findings.append(
                        Finding(
                            severity="error",
                            check="unknown_masking_strategy",
                            model=model.name,
                            column=column.name,
                            message=(
                                f"unknown masking strategy {column.masking!r}; "
                                f"valid: {', '.join(sorted(policy.masking_strategies))}"
                            ),
                        )
                    )
                elif column.masking == "tokenize":
                    report.findings.append(
                        Finding(
                            severity="error",
                            check="unimplemented_masking_strategy",
                            model=model.name,
                            column=column.name,
                            message=(
                                "'tokenize' is declared in policy.yml but "
                                "deliberately not implemented -- it requires a real "
                                "token vault. Use 'hash' if a one-way pseudonym is "
                                "what you want."
                            ),
                        )
                    )

            if (
                column.is_pii
                and column.masking is None
                and policy.rank(column.classification) > policy.rank("internal")
            ):
                report.findings.append(
                    Finding(
                        severity="warning",
                        check="pii_without_masking_strategy",
                        model=model.name,
                        column=column.name,
                        message=(
                            "marked pii above internal clearance with no masking "
                            "strategy, so it will be redacted by the fail-safe "
                            "default. That is safe but probably not deliberate -- "
                            "declare `masking:` explicitly."
                        ),
                    )
                )

        report.coverage_by_layer[model.layer] = (layer_total, layer_explicit)

    return report


def print_report(report: Report, models: list[Model]) -> None:
    print("tradeflow classification coverage")
    print("=" * 72)
    print(f"  models inspected      {len(models)}")
    print(f"  columns in warehouse  {report.total_columns}")
    print(f"  explicitly tagged     {report.explicit_columns}")
    print(f"  flagged as PII        {report.pii_columns}")
    print(f"  documented exemptions {report.exemptions}")
    print(
        f"  inheriting default    {report.inherited_columns} "
        "(derived mart columns -- see policy.yml)"
    )
    print()
    print(
        f"  REQUIRED COVERAGE     {report.required_covered}/{report.required_columns} "
        f"= {report.coverage:.1f}%"
    )
    print("    (staging in full, plus every column of any PII-bearing model)")
    print()
    print("  tagged columns by layer:")
    for layer in sorted(report.coverage_by_layer):
        total, explicit = report.coverage_by_layer[layer]
        share = 100.0 * explicit / total if total else 100.0
        print(f"    {layer:<18} {explicit:>4}/{total:<4} tagged  ({share:5.1f}%)")

    if report.info:
        print()
        print(f"  {len(report.info)} documented exemption(s):")
        for finding in report.info:
            print(f"    i {finding.model}.{finding.column}")
            print(f"        {finding.message}")

    if report.warnings:
        print()
        print(f"  {len(report.warnings)} warning(s):")
        for finding in report.warnings:
            print(f"    ~ {finding.model}.{finding.column} [{finding.check}]")
            print(f"        {finding.message}")

    if report.errors:
        print()
        print(f"  {len(report.errors)} error(s):")
        for finding in report.errors:
            print(f"    x {finding.model}.{finding.column} [{finding.check}]")
            print(f"        {finding.message}")
        print()
        print("  FAILED -- every column above needs a classification decision.")
    else:
        print()
        print("  PASSED -- every column requiring a classification has one.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable findings."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors.",
    )
    args = parser.parse_args(argv)

    try:
        policy = Policy.load()
        models = load_models(policy=policy, include_generated=False)
    except PolicyError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    report = check(policy, models)

    if args.json:
        print(
            json.dumps(
                {
                    "coverage_percent": round(report.coverage, 2),
                    "total_columns": report.total_columns,
                    "explicit_columns": report.explicit_columns,
                    "pii_columns": report.pii_columns,
                    "findings": [vars(f) for f in report.findings],
                },
                indent=2,
            )
        )
    else:
        print_report(report, models)

    failed = bool(report.errors) or (args.strict and bool(report.warnings))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
