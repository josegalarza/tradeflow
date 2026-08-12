#!/usr/bin/env python
"""CI gate: models may only reference the layer below them, or their own.

The layered architecture in the README is only real if something enforces it.
Left to convention, the first mart that reads a staging model directly is a
five-minute shortcut, and eighteen months later the layers are a diagram that
describes nothing.

The permitted edges:

    10_staging       <- sources only
    20_intermediate  <- 10_staging, 20_intermediate
    30_marts         <- 20_intermediate, 30_marts
    40_secure        <- 30_marts

Two exceptions are allowed and both are declared here rather than being quietly
tolerated, because an unexplained exception is indistinguishable from a
violation:

* marts may read staging for *reference* lookups (prices, FX). Routing a
  three-column reference join through an intermediate model that does nothing but
  rename it adds a layer of indirection and no clarity;
* staging may not reference other models at all -- that is what makes staging
  cheap to reason about.

Usage::

    python -m governance.check_layer_boundaries
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from governance.policy import Model, PolicyError, load_models

#: layer -> layers it is allowed to reference.
ALLOWED_REFERENCES: dict[str, set[str]] = {
    "10_staging": set(),
    "20_intermediate": {"10_staging", "20_intermediate"},
    "30_marts": {"20_intermediate", "30_marts"},
    "40_secure": {"30_marts"},
}

#: Reference models a mart may read straight from staging. Each entry is a
#: deliberate decision: these are small, slowly-changing lookups where an
#: intervening intermediate model would only rename columns.
REFERENCE_MODEL_EXCEPTIONS: set[str] = {
    "stg_market_prices",
    "stg_fx_rates",
    "stg_instruments",
    "stg_accounts",
    "stg_cash_movements",
    "stg_app_events",
}

#: Whole-model exemptions, each with a written reason -- the same principle as the
#: classification exemptions in governance/policy.yml. An exception is allowed;
#: an exception nobody can explain is a violation with better paperwork. The
#: reason is printed on every run so it stays visible rather than accumulating
#: silently.
MODEL_EXEMPTIONS: dict[str, str] = {
    "dim_date": (
        "The calendar spine has to span every date that appears anywhere in the "
        "warehouse, so it reads MIN/MAX from the activity models directly. "
        "Sourcing the range from 20_intermediate instead would cover only rows "
        "that survived quarantine, and cash movements and app events have no "
        "intermediate model at all. It reads bounds, never business logic, and it "
        "is the one model that legitimately sits outside the layer flow."
    ),
}


def _wrap(text: str, width: int) -> list[str]:
    import textwrap

    return textwrap.wrap(" ".join(text.split()), width=width)


def check(models: list[Model]) -> list[str]:
    by_name = {model.name: model for model in models}
    violations: list[str] = []

    for model in models:
        if model.name in MODEL_EXEMPTIONS:
            continue
        allowed = ALLOWED_REFERENCES.get(model.layer)
        if allowed is None:
            violations.append(
                f"{model.name}: lives in unknown layer {model.layer!r}. Add it to "
                "ALLOWED_REFERENCES or move the file into a known layer directory."
            )
            continue

        for dependency_id in model.depends_on:
            # Sources are always fine; only model-to-model edges are constrained.
            if not dependency_id.startswith("model."):
                continue
            dependency_name = dependency_id.split(".")[-1]
            dependency = by_name.get(dependency_name)
            if dependency is None:
                continue

            if dependency.layer in allowed:
                continue
            if (
                model.layer == "30_marts"
                and dependency.layer == "10_staging"
                and dependency.name in REFERENCE_MODEL_EXCEPTIONS
            ):
                continue

            violations.append(
                f"{model.name} ({model.layer}) references {dependency.name} "
                f"({dependency.layer}). Permitted: "
                f"{', '.join(sorted(allowed)) or 'sources only'}"
                + (
                    ". If this is a legitimate reference lookup, add it to "
                    "REFERENCE_MODEL_EXCEPTIONS with a reason."
                    if model.layer == "30_marts"
                    else "."
                )
            )

    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.parse_args(argv)

    try:
        models = load_models()
    except PolicyError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    violations = check(models)

    counts: dict[str, int] = {}
    for model in models:
        counts[model.layer] = counts.get(model.layer, 0) + 1

    print("tradeflow layer boundaries")
    print("=" * 72)
    for layer in sorted(counts):
        allowed = ALLOWED_REFERENCES.get(layer)
        permitted = ", ".join(sorted(allowed)) if allowed else "sources only"
        print(f"  {layer:<18} {counts[layer]:>3} models   <- {permitted}")

    if MODEL_EXEMPTIONS:
        print()
        print(f"  {len(MODEL_EXEMPTIONS)} documented exemption(s):")
        for name, reason in sorted(MODEL_EXEMPTIONS.items()):
            print(f"    i {name}")
            for line in _wrap(reason, width=68):
                print(f"        {line}")

    if violations:
        print()
        print(f"  {len(violations)} violation(s):")
        for violation in violations:
            print(f"    x {violation}")
        print()
        print("  FAILED -- the layering is a claim the README makes; keep it true.")
        return 1

    print()
    print("  PASSED -- every reference respects the layer ordering.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
