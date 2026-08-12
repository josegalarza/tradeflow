# 0004 — SCD2 built from periodic extracts, not `dbt snapshot`

**Status:** accepted · **Date:** 2026-08-12

## Context

`dim_customer` is a Type 2 dimension: one row per customer per version of their
attributes, so that a trade placed while a customer was rated `medium` risk stays
attributed to `medium` risk after compliance moves them to `high`.

dbt's idiomatic tool for this is `dbt snapshot`. It was rejected, and the reason
is worth writing down because "why didn't you just use snapshots" is the first
question a dbt-literate reviewer will ask.

## Decision

The generator emits **month-end full extracts** of the mutable customer record —
one row per customer per extract date, holding that customer's state as at that
date. `int_customer_versions` reconstructs SCD2 from those extracts with window
functions.

## Why not `dbt snapshot`

**Snapshots can only accumulate history by being run repeatedly over real elapsed
time.** That single property makes them unusable here:

- A reviewer cloning the repo and running `make demo` would get a snapshot table
  with exactly one version per customer. The entire Type 2 story — the thing this
  model exists to demonstrate — would be invisible on a fresh clone.
- CI cannot assert anything about it. There is no way to test that version
  boundaries are contiguous and non-overlapping when the data has only ever been
  observed once.
- The unit tests in `_intermediate__unit_tests.yml` would not exist. Those tests
  are what caught the boundary convention questions, and they only work because
  the logic is deterministic SQL over fixed inputs rather than a stateful merge.

**The extract shape is also more faithful to the common case.** A nightly full
dump of a mutable source table into object storage is what a great many
warehouses actually receive. Snapshots exist precisely because that dump is often
*absent*; where it exists, reconstructing history from it is normal practice.

## The implementation

Three steps, in `int_customer_versions`:

1. Hash the tracked attributes per (customer, extract). Hashing rather than
   comparing fourteen columns pairwise means adding a tracked attribute is a
   one-line change instead of a fourteen-clause boolean.
2. Keep only extracts where the hash differs from that customer's previous
   extract. Everything else is an unchanged re-observation, which would otherwise
   add a row per customer per month forever.
3. Close each version the day before the next opens; leave the last open at
   `9999-12-31`.

## Two conventions, chosen deliberately

**Version 1's `valid_from` is the customer's `created_at`, not the first extract
date.** The customer existed from the moment they signed up. Dating their first
version from an accident of extract scheduling leaves a gap that every
`valid_from <= date <= valid_to` join silently drops.

**`valid_to` is inclusive.** Half-open intervals are the more common convention
and are easier to reason about, but they make `BETWEEN` wrong — and `BETWEEN` is
what an analyst writes. Choosing the convention that matches how the table will
actually be queried avoids a class of off-by-one that produces plausible,
slightly wrong numbers.

The cost is that `dbt_utils.mutually_exclusive_ranges` cannot be used: it assumes
half-open bounds and reports every correct boundary as a one-day gap. A test that
has to be configured to ignore the convention it is checking is not checking
anything, so `tests/assert_customer_scd2_windows_are_sound.sql` is written out
instead — checking overlaps, gaps, inverted windows and the exactly-one-current
invariant.

## Consequences

- History is only as granular as the extract cadence. A change and a reversal
  inside one month are invisible. This is true of any extract-based reconstruction
  and is the honest trade for reproducibility.
- The facts resolve their customer key with an `ASOF JOIN` on the event date.
  Getting this wrong is the classic Type 2 error in both directions — joining on
  `is_current` attributes every historical trade to today's attributes, and
  joining on `customer_id` alone multiplies every fact by the version count. A
  row-count parity test on `fct_executions` guards it.
