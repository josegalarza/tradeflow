#!/usr/bin/env python
"""Print one customer as each role sees them.

The fastest way to tell whether a masking framework does anything is to look at
the same row through every lens. This is `make roles`, and it is the thing to run
after changing a classification tag.

Usage::

    python scripts/show_roles.py
    python scripts/show_roles.py --customer CUS-0000000027
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb

from dashboard.data import database_path
from governance.policy import Policy

COLUMNS = [
    "full_name",
    "email",
    "phone_number",
    "national_id",
    "date_of_birth",
    "street_address",
    "city",
    "postcode",
    "risk_rating",
    "kyc_status",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--customer", help="Customer ID. Defaults to the first found.")
    args = parser.parse_args(argv)

    path = database_path()
    if not path.exists():
        print(f"no warehouse at {path}. Run `make demo` first.", file=sys.stderr)
        return 1

    policy = Policy.load()
    connection = duckdb.connect(str(path), read_only=True)

    customer_id = args.customer
    if not customer_id:
        row = connection.execute(
            """
            SELECT customer_id FROM marts.dim_customer
            WHERE is_current AND postcode IS NOT NULL AND national_id IS NOT NULL
            LIMIT 1
            """
        ).fetchone()
        if not row:
            print("no customers in the warehouse yet.", file=sys.stderr)
            return 1
        customer_id = row[0]

    print()
    print(f"Customer {customer_id}, as seen through each role's schema")
    print("=" * 78)

    def show(title: str, note: str, schema: str, table: str) -> None:
        available = {
            name
            for (name,) in connection.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = ? AND table_name = ?
                """,
                [schema, table],
            ).fetchall()
        }
        selected = [column for column in COLUMNS if column in available]
        withheld = [column for column in COLUMNS if column not in available]

        print()
        print(f"  {title}")
        print(f"    {note}")
        print("    " + "-" * 72)
        if not selected:
            print(
                f"    none of these columns are present -- the view exposes "
                f"{len(available)} other columns"
            )
            print("    (segments, tiers, cohorts and engagement, but no identity)")
            return

        record = connection.execute(
            f"""
            SELECT {", ".join(selected)} FROM "{schema}"."{table}"
            WHERE customer_id = ? AND is_current
            """,
            [customer_id],
        ).fetchone()
        for name, value in zip(selected, record or [], strict=False):
            display = "NULL (redacted)" if value is None else str(value)
            print(f"    {name:<18} {display}")
        for name in withheld:
            print(f"    {name:<18} -- column absent from this view --")

    show(
        "marts.dim_customer",
        "The unmasked dimension. Data team only; no role is granted this schema.",
        "marts",
        "dim_customer",
    )

    for role_name in sorted(policy.roles):
        role = policy.roles[role_name]
        note = " ".join((role.get("description") or "").split())
        show(
            f"{role['schema']}.{role_name}__dim_customer",
            f"clearance {role['clearance']} -- {note[:96]}",
            role["schema"],
            f"{role_name}__dim_customer",
        )

    print()
    print("  All four views are generated from the classification tags by")
    print("  governance/generate_secure_views.py. Nothing here is hand-written.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
