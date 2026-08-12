#!/usr/bin/env python
"""Render the data catalog to docs/catalog.md from the dbt artefacts.

A catalog nobody maintains is worse than no catalog, because people trust it.
This one is generated from the same tags that drive the masking, so it cannot
drift from what the warehouse actually does: if the catalog says a column is
hashed for analysts, that is because the analyst view hashes it.

What it produces, in order of usefulness to a reader:

* a governance summary -- column counts by classification, PII by category,
  which roles see what;
* a PII register: every personal-data column, its type, its masking strategy,
  and which roles can read it unmasked. This is the artefact a subject-access or
  breach-assessment request actually needs;
* documented exemptions, so every deliberate deviation is visible in one place;
* per-model column tables for the whole warehouse.

Usage::

    python -m governance.build_catalog
    python -m governance.build_catalog --out docs/catalog.md
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from governance.policy import (
    REPO_ROOT,
    Model,
    Policy,
    PolicyError,
    load_models,
)

DEFAULT_OUT = REPO_ROOT / "docs" / "catalog.md"

BADGE = {
    "public": "PUBLIC",
    "internal": "INTERNAL",
    "confidential": "CONFIDENTIAL",
    "restricted": "RESTRICTED",
}


def role_visibility(policy: Policy, column, models_role_scope: bool) -> str:
    """How each role sees this column, as a compact cell."""
    if not models_role_scope:
        return "_not exposed to roles_"

    parts = []
    for role_name in sorted(policy.roles):
        if policy.is_dropped_for_role(column, role_name):
            parts.append(f"{role_name}: withheld")
            continue
        strategy = policy.resolve_masking(column, role_name)
        parts.append(f"{role_name}: {'clear' if strategy == 'none' else strategy}")
    return "<br>".join(parts)


def render(policy: Policy, models: list[Model]) -> str:
    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []

    counts: Counter[str] = Counter()
    pii_by_type: Counter[str] = Counter()
    pii_columns: list[tuple[Model, object]] = []
    exemptions: list[tuple[Model, object]] = []

    for model in models:
        for column in model.columns:
            if not column.in_database:
                continue
            counts[column.classification] += 1
            if column.is_pii:
                pii_by_type[column.pii_type or "unspecified"] += 1
                pii_columns.append((model, column))
            if column.rationale:
                exemptions.append((model, column))

    total = sum(counts.values())

    # -- header ------------------------------------------------------------ #
    lines += [
        "# tradeflow data catalog",
        "",
        "> **Generated file.** Written by `governance/build_catalog.py` from the",
        "> dbt manifest and `governance/policy.yml`. Run `make governance` to",
        "> refresh. Do not edit by hand.",
        "",
        f"Generated {generated_at}",
        "",
        "This catalog is produced from the same classification tags that generate",
        "the masked role views in `warehouse/models/40_secure/`. It therefore",
        "cannot disagree with what the warehouse does -- if a column is listed here",
        "as hashed for analysts, it is hashed because this row and that view come",
        "from one source.",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"- **{len(models)}** models across {len(set(m.layer for m in models))} layers",
        f"- **{total}** columns classified",
        f"- **{len(pii_columns)}** columns carrying personal data",
        f"- **{len(policy.roles)}** access roles",
        f"- **{len(exemptions)}** documented classification exemptions",
        "",
        "### Columns by classification",
        "",
        "| Classification | Columns | Share | Meaning |",
        "|---|--:|--:|---|",
    ]
    for name in sorted(policy.classifications, key=lambda c: policy.rank(c)):
        count = counts.get(name, 0)
        share = 100.0 * count / total if total else 0.0
        meaning = " ".join(
            (policy.classifications[name].get("description") or "").split()
        )
        lines.append(f"| `{name}` | {count} | {share:.1f}% | {meaning} |")

    lines += [
        "",
        "### Personal data by category",
        "",
        "| Category | Columns |",
        "|---|--:|",
    ]
    for pii_type, count in pii_by_type.most_common():
        lines.append(f"| `{pii_type}` | {count} |")

    # -- roles ------------------------------------------------------------- #
    lines += [
        "",
        "---",
        "",
        "## Access roles",
        "",
        "| Role | Schema | Clearance | Above clearance | Purpose |",
        "|---|---|---|---|---|",
    ]
    for role_name in sorted(policy.roles):
        role = policy.roles[role_name]
        behaviour = "withheld entirely" if role.get("drop_above_clearance") else "masked"
        purpose = " ".join((role.get("description") or "").split())
        lines.append(
            f"| `{role_name}` | `{role['schema']}` | `{role['clearance']}` | "
            f"{behaviour} | {purpose} |"
        )

    lines += [
        "",
        "### Masking strategies",
        "",
        "| Strategy | Behaviour |",
        "|---|---|",
    ]
    for name in sorted(policy.masking_strategies):
        description = " ".join(
            (policy.masking_strategies[name].get("description") or "").split()
        )
        lines.append(f"| `{name}` | {description} |")

    # -- PII register ------------------------------------------------------ #
    lines += [
        "",
        "---",
        "",
        "## PII register",
        "",
        "Every column carrying personal data, with how each role sees it. This is",
        "the table to reach for when answering a subject-access request or",
        "assessing the blast radius of a credential leak.",
        "",
        "| Model | Column | Category | Classification | Strategy | Per-role visibility |",
        "|---|---|---|---|---|---|",
    ]
    for model, column in sorted(
        pii_columns, key=lambda pair: (pair[0].layer, pair[0].name, pair[1].name)
    ):
        in_scope = policy.in_secure_scope(model)
        lines.append(
            f"| `{model.name}` | `{column.name}` | "
            f"{column.pii_type or '-'} | `{column.classification}` | "
            f"`{column.masking or 'redact (default)'}` | "
            f"{role_visibility(policy, column, in_scope)} |"
        )

    # -- exemptions -------------------------------------------------------- #
    if exemptions:
        lines += [
            "",
            "---",
            "",
            "## Documented exemptions",
            "",
            "Columns classified below the level their name would imply. Each one",
            "requires a written rationale to pass CI -- exceptions are permitted,",
            "undocumented exceptions are not.",
            "",
        ]
        for model, column in exemptions:
            lines += [
                f"### `{model.name}.{column.name}`",
                "",
                f"Classified `{column.classification}`.",
                "",
                "> " + " ".join(column.rationale.split()),
                "",
            ]

    # -- per-model detail -------------------------------------------------- #
    lines += ["", "---", "", "## Models", ""]

    by_layer: dict[str, list[Model]] = defaultdict(list)
    for model in models:
        by_layer[model.layer].append(model)

    for layer in sorted(by_layer):
        lines += [f"### Layer `{layer}`", ""]
        for model in by_layer[layer]:
            pii_note = " **contains PII**" if model.contains_pii else ""
            lines += [f"#### `{model.name}`{pii_note}", ""]
            if model.grain:
                lines.append(f"**Grain:** {model.grain}  ")
            if model.kimball_type:
                lines.append(f"**Type:** `{model.kimball_type}`  ")
            lines.append(f"**Materialization:** `{model.materialization}`")
            lines.append("")
            if model.description:
                lines += [" ".join(model.description.split()), ""]

            documented = [
                column
                for column in model.columns
                if column.in_database
                and (column.description or column.classification_source == "explicit")
            ]
            if documented:
                lines += [
                    "| Column | Type | Classification | PII | Masking | Description |",
                    "|---|---|---|---|---|---|",
                ]
                for column in documented:
                    description = " ".join((column.description or "").split())
                    lines.append(
                        f"| `{column.name}` | `{column.data_type or '?'}` | "
                        f"`{column.classification}` | "
                        f"{('yes (' + (column.pii_type or '?') + ')') if column.is_pii else '-'} | "
                        f"`{column.masking or '-'}` | {description} |"
                    )
                lines.append("")

            undocumented = [
                column.name
                for column in model.columns
                if column.in_database
                and column.classification_source in ("layer_default", "undocumented")
            ]
            if undocumented:
                lines += [
                    f"<details><summary>{len(undocumented)} derived columns "
                    f"inheriting the layer default "
                    f"(`{column.classification}`)</summary>",
                    "",
                    ", ".join(f"`{name}`" for name in undocumented),
                    "",
                    "</details>",
                    "",
                ]

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    try:
        policy = Policy.load()
        models = load_models(policy=policy, include_generated=False)
    except PolicyError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    content = render(policy, models)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(content)
    lines = content.count("\n")
    print(f"wrote {args.out.relative_to(REPO_ROOT)} ({lines} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
