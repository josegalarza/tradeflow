# 0003 — Tag-driven masking, generated into per-role views

**Status:** accepted · **Date:** 2026-08-12

## Context

The warehouse holds names, emails, phone numbers, dates of birth, national
identifiers, street addresses and raw IP addresses. Something has to decide who
sees what, and that decision has to survive people adding columns for years after
the framework is built.

DuckDB has no row-level security, no dynamic data masking and no policy tags. So
the question is not "which engine feature do we use" but "where does the control
live, and what exactly does it protect against".

## Decision

Classification metadata on every column in the dbt schema files
(`meta.classification`, `meta.pii`, `meta.pii_type`, `meta.masking`) is the single
source of truth. Three tools read it out of `manifest.json`:

| Tool | Purpose |
|---|---|
| `check_classification.py` | CI gate: an untagged column cannot merge |
| `generate_secure_views.py` | Emits one view per role per mart, masking applied |
| `build_catalog.py` | Renders `docs/catalog.md`, including the PII register |

The intended deployment is that each role is granted its own schema
(`secure_analyst`, `secure_support`, …) and nothing else.

## What this protects against, precisely

It protects against **an authorised user of a role's schema reading data above
their clearance**. Within that boundary it is a real control: the masking is
applied in the view definition, and there is no query a role can write against
its own schema that recovers the underlying value.

It does **not** protect against anyone with direct access to `marts`. That is a
grant, not a mask, and this framework has nothing to say about it.

Being exact about this matters more than the demo looking impressive. A reader who
concludes "masked views therefore secure" has been misled, and the fix is to say
so in the policy file, the generated README and here.

## Design decisions worth defending

**Generated, not hand-written.** Four roles across ten marts is forty views and
about two thousand column decisions. Hand-written, they would be inconsistent
within a month, and the failure is silent — a column added to a mart and forgotten
in one role's view leaks. Generating them means the policy is the only thing
anyone edits.

**Generated files are committed.** They are real dbt models: they belong in the
DAG, the docs and the lineage graph, and a reviewer should be able to read the
exact SQL a role sees without running a generator. CI runs the generator with
`--check` and fails if the committed views no longer match the policy.

**It fails closed.** A column above a role's clearance with no declared masking
strategy is *redacted*, not passed through. A governance framework that fails
open is worse than none, because it is trusted. The CI gate means this default
should never fire; it exists for the day the gate is bypassed.

**Exceptions are allowed, but must be written down.** `ip_address_prefix` is a
deliberately truncated /24 that exists so analysts have a safe alternative to the
raw address. Classifying it `confidential` would put it out of reach of the people
it was built for, who would then reach for the raw column instead — strictly
worse. It passes the gate only because it declares
`meta.classification_rationale`, which is rendered into the catalog. Undocumented
exceptions fail.

**`tokenize` is declared and deliberately unimplemented.** Reversible
pseudonymisation needs a token vault with its own access control and key
rotation. Requesting it raises an error rather than silently substituting a hash,
because a fake token vault misrepresents the control to whoever reads the catalog.

**The hash is salted, from the environment.** An unsalted hash of an email address
is reversible by anyone with a wordlist. It would look exactly like a working
control and provide none of the substance.

## Consequences

- Access enforcement depends on schema grants being set up correctly outside this
  repo. The repo can generate the views; it cannot grant them.
- Masking changes a column's type — a generalised date becomes a string band — so
  the secure views are not drop-in replacements for the marts.
- The same tags would drive Snowflake masking policies or BigQuery policy tags,
  where the engine enforces and bypass is impossible. The metadata is portable;
  only the enforcement mechanism is not.
