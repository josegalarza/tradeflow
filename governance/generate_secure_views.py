#!/usr/bin/env python
"""Generate the 40_secure role views from classification tags.

For every role in ``policy.yml`` and every in-scope mart, emits a dbt model that
selects the same columns with masking already applied. The intended deployment is
that each role holds grants on its own schema and nothing else, so the masking is
not something a query can opt out of.

Why generate rather than hand-write: four roles across ten marts is forty views
and roughly two thousand column decisions. Written by hand, they would be
inconsistent within a month and wrong within a quarter, and the interesting
failure is silent -- a column added to a mart and forgotten in one role's view
leaks. Generating them means the policy is the only thing anyone edits, and
``--check`` in CI proves the checked-in views still match it.

The generated files ARE committed. They are real dbt models: they need to appear
in the DAG, in the docs and in the lineage graph, and a reviewer should be able
to read the exact SQL a role sees without running a generator first.

Usage::

    python -m governance.generate_secure_views            # write the files
    python -m governance.generate_secure_views --check    # CI: verify up to date
    python -m governance.generate_secure_views --role analyst --diff
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from governance.policy import (
    REPO_ROOT,
    Column,
    Model,
    Policy,
    PolicyError,
    load_models,
)

SECURE_DIR = REPO_ROOT / "warehouse" / "models" / "40_secure"

GENERATED_BANNER = """\
{#
  GENERATED FILE -- DO NOT EDIT.

  Written by governance/generate_secure_views.py from the classification tags in
  the dbt schema YAML and the role definitions in governance/policy.yml.

  To change what this role can see, edit the policy or the column's tags and run
  `make governance`. Editing this file directly will be reverted by the next
  generation, and CI checks that it matches.
#}
"""


def masking_expression(policy: Policy, column: Column, strategy: str) -> str:
    """Render the macro call that applies ``strategy`` to ``column``.

    The choice of macro depends on the column's semantic type, not just the
    strategy name: generalising a date of birth to a decade and generalising a
    postcode to its prefix are the same policy decision and entirely different
    SQL. Dispatching on ``pii_type`` first and the physical type second is what
    lets the policy stay declarative.
    """
    name = column.name
    data_type = column.data_type or "VARCHAR"
    upper_type = data_type.upper()

    if strategy == "none":
        return name

    if strategy == "hash":
        return f"{{{{ mask_hash('{name}') }}}}"

    if strategy == "partial":
        if column.pii_type == "email":
            return f"{{{{ mask_partial_email('{name}') }}}}"
        if column.pii_type == "phone":
            return f"{{{{ mask_partial_phone('{name}') }}}}"
        return f"{{{{ mask_partial_generic('{name}') }}}}"

    if strategy == "redact":
        return f"{{{{ mask_redact('{name}', '{data_type}') }}}}"

    if strategy == "generalize":
        # Physical type is checked BEFORE the semantic pii_type, because it
        # determines which SQL is even valid. `age_years` is derived from a date
        # of birth and tagged as such, but it is an INTEGER -- dispatching on the
        # semantic type first would emit YEAR(age_years) and fail at build time.
        if "TIMESTAMP" in upper_type:
            return f"{{{{ mask_generalize_timestamp('{name}') }}}}"
        if upper_type.startswith("DATE"):
            return f"{{{{ mask_generalize_date('{name}') }}}}"
        if any(
            token in upper_type
            for token in ("INT", "DECIMAL", "DOUBLE", "FLOAT", "NUMERIC", "HUGEINT")
        ):
            return f"{{{{ mask_generalize_numeric('{name}') }}}}"
        if column.pii_type == "address" or "postcode" in name or "zip" in name:
            return f"{{{{ mask_generalize_postcode('{name}') }}}}"
        return f"{{{{ mask_partial_generic('{name}') }}}}"

    raise PolicyError(
        f"no SQL implementation for masking strategy {strategy!r} "
        f"(column {name!r}). Add a macro in warehouse/macros/masking.sql and a "
        "branch here."
    )


def render_model(policy: Policy, model: Model, role_name: str) -> str:
    """Render one role's view over one mart."""
    role = policy.role(role_name)
    lines: list[str] = [GENERATED_BANNER]

    dropped: list[str] = []
    masked: list[tuple[str, str]] = []
    select_lines: list[str] = []

    for column in model.columns:
        # Documented in YAML but not present in the built warehouse. Emitting it
        # would produce a view that fails to bind, and the error would point here
        # rather than at the stale schema file that caused it.
        # check_classification.py reports these as warnings.
        if not column.in_database:
            continue

        if policy.is_dropped_for_role(column, role_name):
            dropped.append(f"{column.name} ({column.classification})")
            continue

        strategy = policy.resolve_masking(column, role_name)
        expression = masking_expression(policy, column, strategy)

        if strategy == "none":
            select_lines.append(f"  {column.name},")
        else:
            masked.append((column.name, strategy))
            select_lines.append(f"  {expression} AS {column.name},")

    # -- header comment: the audit trail for this view --------------------- #
    lines.append("/*")
    lines.append(f"  {model.name} as seen by the `{role_name}` role.")
    lines.append("")
    lines.append(f"  Role clearance : {role['clearance']}")
    lines.append(f"  Source model   : {model.schema}.{model.name}")
    lines.append(
        f"  Columns        : {len(select_lines)} exposed, "
        f"{len(masked)} masked, {len(dropped)} withheld"
    )
    if masked:
        lines.append("")
        lines.append("  Masked:")
        for name, strategy in masked:
            lines.append(f"    {name:<34} {strategy}")
    if dropped:
        lines.append("")
        lines.append("  Withheld entirely (above clearance, and this role omits")
        lines.append("  rather than masks -- a masked column still advertises that")
        lines.append("  the data exists):")
        for entry in dropped:
            lines.append(f"    {entry}")
    lines.append("*/")
    lines.append("")

    # -- config ------------------------------------------------------------ #
    lines.append("{{")
    lines.append("  config(")
    lines.append(f"    schema = '{role['schema']}',")
    lines.append("    materialized = 'view',")
    lines.append(f"    tags = ['secure', 'governance', 'role:{role_name}'],")
    lines.append("  )")
    lines.append("}}")
    lines.append("")

    if not select_lines:
        # Every column withheld. Emitting a view with no columns is invalid SQL,
        # and emitting nothing would silently drop the model from the DAG.
        raise PolicyError(
            f"role {role_name!r} would see zero columns of {model.name!r}. "
            "Either exclude the model in policy.yml's secure_view_scope or give "
            "the role an override -- generating an empty view would fail at build "
            "time with a far less obvious message."
        )

    lines.append("SELECT")
    lines.extend(select_lines)
    lines.append(f"FROM {{{{ ref('{model.name}') }}}}")
    lines.append("")

    return "\n".join(lines)


def render_schema_yml(policy: Policy, models: list[Model]) -> str:
    """Schema file for the generated views, so they are documented too."""
    lines = [
        "version: 2",
        "",
        "# GENERATED FILE -- DO NOT EDIT.",
        "# Written by governance/generate_secure_views.py.",
        "#",
        "# One view per role per in-scope mart. Each role's schema is what that",
        "# role would be granted access to; `marts` itself is granted to nobody",
        "# outside the data team.",
        "",
        "models:",
    ]
    for role_name in sorted(policy.roles):
        role = policy.roles[role_name]
        for model in models:
            lines.append(f"  - name: {role_name}__{model.name}")
            lines.append("    description: >")
            lines.append(
                f"      {model.name} as seen by the `{role_name}` role "
                f"(clearance: {role['clearance']}). Masking applied per"
            )
            lines.append("      governance/policy.yml. Generated -- do not edit by hand.")
            lines.append("    meta:")
            lines.append('      layer: "40_secure"')
            lines.append(f"      role: {role_name}")
            lines.append(f"      source_model: {model.name}")
            lines.append("      generated: true")
            lines.append("")
    return "\n".join(lines)


def render_readme(policy: Policy, models: list[Model]) -> str:
    role_lines = []
    for role_name in sorted(policy.roles):
        role = policy.roles[role_name]
        role_lines.append(
            f"| `{role_name}` | `{role['schema']}` | {role['clearance']} | "
            f"{' '.join((role.get('description') or '').split())} |"
        )

    return f"""\
# 40_secure -- generated role views

**Every file in this directory is generated. Do not edit them.**

They are written by `governance/generate_secure_views.py` from two inputs:

- the `meta.classification` / `meta.masking` tags on the model columns, and
- the role definitions in `governance/policy.yml`.

Run `make governance` to regenerate. CI runs the generator with `--check` and
fails if the committed files no longer match the policy, so a column added to a
mart cannot quietly stay unmasked in one role's view.

## Roles

| Role | Schema | Clearance | Purpose |
|---|---|---|---|
{chr(10).join(role_lines)}

## Scope

{len(models)} mart models x {len(policy.roles)} roles = \
{len(models) * len(policy.roles)} views.

Staging and intermediate are deliberately out of scope: they are the engineering
layer, and generating role views over them would imply somebody outside the data
team should be querying them.

## What this is and is not

These views enforce policy at the *modelling* layer. Granting a role its own
schema and nothing else is a real control in a warehouse where access is mediated
by grants -- and it is not engine-enforced masking. Anyone with direct access to
`marts` bypasses it completely.

DuckDB has no native dynamic data masking or row-level security, so this is the
strongest available form here. The same tags would drive Snowflake masking
policies or BigQuery policy tags, where the engine itself does the enforcing and
bypass is not possible.
"""


def generate(policy: Policy, models: list[Model], target: Path) -> dict[Path, str]:
    """Build the full set of files that should exist, as path -> content."""
    in_scope = [model for model in models if policy.in_secure_scope(model)]
    if not in_scope:
        raise PolicyError(
            "no models are in secure_view_scope. Check that the warehouse has "
            "been built and that policy.yml's include_layers matches the model "
            "directory names."
        )

    files: dict[Path, str] = {}
    for role_name in sorted(policy.roles):
        for model in in_scope:
            path = target / role_name / f"{role_name}__{model.name}.sql"
            files[path] = render_model(policy, model, role_name)

    files[target / "_secure__models.yml"] = render_schema_yml(policy, in_scope)
    files[target / "README.md"] = render_readme(policy, in_scope)
    return files


def write(files: dict[Path, str], target: Path) -> tuple[int, int]:
    """Write the files, removing any stale generated ones."""
    written = 0
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text() != content:
            path.write_text(content)
            written += 1

    # A role removed from the policy must lose its directory, or its views keep
    # building and keep granting access to a role that no longer exists.
    removed = 0
    if target.exists():
        for existing in sorted(target.rglob("*")):
            if existing.is_file() and existing not in files:
                existing.unlink()
                removed += 1
        for directory in sorted(target.rglob("*"), reverse=True):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
    return written, removed


def check(files: dict[Path, str], target: Path, show_diff: bool) -> list[str]:
    """Return a list of discrepancies between generated and committed files."""
    problems: list[str] = []
    for path, content in sorted(files.items()):
        relative = path.relative_to(REPO_ROOT)
        if not path.exists():
            problems.append(f"missing: {relative}")
            continue
        current = path.read_text()
        if current != content:
            problems.append(f"stale:   {relative}")
            if show_diff:
                diff = difflib.unified_diff(
                    current.splitlines(keepends=True),
                    content.splitlines(keepends=True),
                    fromfile=f"committed/{relative}",
                    tofile=f"generated/{relative}",
                )
                problems.extend(line.rstrip("\n") for line in diff)

    if target.exists():
        for existing in sorted(target.rglob("*.sql")):
            if existing not in files:
                problems.append(
                    f"orphan:  {existing.relative_to(REPO_ROOT)} "
                    "(no longer produced by the policy)"
                )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the committed views match the policy. Writes nothing.",
    )
    parser.add_argument(
        "--diff", action="store_true", help="With --check, print the differences."
    )
    parser.add_argument("--role", help="Limit generation to one role (for inspection).")
    parser.add_argument("--out", type=Path, default=SECURE_DIR, help="Output directory.")
    args = parser.parse_args(argv)

    try:
        policy = Policy.load()
        if args.role:
            role = policy.role(args.role)
            policy.roles = {args.role: role}
        models = load_models(policy=policy)
        files = generate(policy, models, args.out)
    except PolicyError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.check:
        problems = check(files, args.out, args.diff)
        if problems:
            print("secure views are out of date with governance/policy.yml:\n")
            for problem in problems:
                print(f"  {problem}")
            print(
                "\nRun `make governance` and commit the result. The generated "
                "views are checked in on purpose so that the SQL each role sees "
                "is reviewable in a pull request."
            )
            return 1
        print(f"secure views up to date ({len(files)} files).")
        return 0

    written, removed = write(files, args.out)
    roles = sorted(policy.roles)
    print(f"generated {len(files)} files for {len(roles)} roles: {', '.join(roles)}")
    print(f"  {written} written or updated, {removed} stale removed")
    print(f"  -> {args.out.relative_to(REPO_ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
