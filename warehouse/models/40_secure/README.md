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
| `analyst` | `secure_analyst` | internal | The default role, and the one most queries should run as. Full access to behaviour, balances and order flow; identity is hashed so cohorts and distinct counts still work. |
| `auditor` | `secure_auditor` | restricted | Compliance and internal audit. Sees everything unmasked -- this role exists so that a legitimate regulatory request never requires someone to be granted access to `marts` directly, which is how temporary exceptions become permanent. |
| `marketing` | `secure_marketing` | internal | Campaign and lifecycle marketing. Segments, tiers, cohorts and engagement only. Cannot see balances, positions, contact details or compliance state -- and cannot see that it is missing. |
| `support` | `secure_support` | confidential | Customer support. Needs to verify who is on the phone and see their account state, and needs neither their national ID nor their full contact details to do it. |

## Scope

10 mart models x 4 roles = 40 views.

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
