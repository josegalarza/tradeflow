"""Tests for the classification and masking framework.

The framework's whole value is that it fails *closed*. These tests are therefore
mostly about the unhappy paths: an undeclared strategy, an untagged sensitive
column, a role that should see nothing. A masking framework that works on the
columns you remembered to tag is not a masking framework.

They run against a synthetic policy and synthetic models rather than the real
project, so they test the resolution rules rather than the current contents of
the warehouse -- otherwise every new column would break them.
"""

from __future__ import annotations

import pytest

from governance.policy import Column, Model, Policy, PolicyError

POLICY_DOCUMENT = {
    "classifications": {
        "public": {"rank": 0, "description": "public"},
        "internal": {"rank": 1, "description": "internal"},
        "confidential": {"rank": 2, "description": "confidential"},
        "restricted": {"rank": 3, "description": "restricted"},
    },
    "masking_strategies": {
        "none": {"description": "pass through"},
        "hash": {"description": "salted hash"},
        "partial": {"description": "partial reveal"},
        "redact": {"description": "typed NULL"},
        "generalize": {"description": "reduce precision"},
        "tokenize": {"description": "not implemented"},
    },
    "roles": {
        "auditor": {
            "schema": "secure_auditor",
            "clearance": "restricted",
            "overrides": {},
        },
        "support": {
            "schema": "secure_support",
            "clearance": "confidential",
            "overrides": {"email": "partial"},
        },
        "analyst": {
            "schema": "secure_analyst",
            "clearance": "internal",
            "overrides": {"balance": "none"},
        },
        "marketing": {
            "schema": "secure_marketing",
            "clearance": "internal",
            "drop_above_clearance": True,
            "overrides": {"consent": "none"},
        },
    },
    "secure_view_scope": {"include_layers": ["30_marts"], "exclude_models": ["dim_date"]},
    "enforcement": {
        "technical_column_prefix": "_",
        "technical_column_classification": "internal",
        "require_full_coverage_in_layers": ["10_staging"],
        "require_full_coverage_when_contains_pii": True,
        "default_classification_by_layer": {"30_marts": "internal"},
        "minimum_classification_for_pii": "confidential",
        "exemption_meta_key": "classification_rationale",
        "suspicious_column_patterns": ["email", "ip_address"],
    },
}


@pytest.fixture
def policy() -> Policy:
    return Policy(POLICY_DOCUMENT)


def column(
    name: str,
    classification: str,
    masking: str | None = None,
    pii_type: str | None = None,
    data_type: str = "VARCHAR",
) -> Column:
    return Column(
        name=name,
        description="",
        classification=classification,
        is_pii=pii_type is not None,
        pii_type=pii_type,
        masking=masking,
        data_type=data_type,
        is_technical=name.startswith("_"),
        classification_source="explicit",
    )


# ---------------------------------------------------------------------------- #
# Clearance
# ---------------------------------------------------------------------------- #


def test_clearance_covers_lower_classifications(policy):
    assert policy.is_visible_to("public", "analyst")
    assert policy.is_visible_to("internal", "analyst")
    assert not policy.is_visible_to("confidential", "analyst")
    assert not policy.is_visible_to("restricted", "analyst")


def test_auditor_sees_everything_unmasked(policy):
    for classification in POLICY_DOCUMENT["classifications"]:
        assert policy.is_visible_to(classification, "auditor")
        assert (
            policy.resolve_masking(
                column("national_id", classification, masking="redact"), "auditor"
            )
            == "none"
        )


def test_unknown_role_and_classification_raise(policy):
    with pytest.raises(PolicyError, match="unknown role"):
        policy.role("chief_executive")
    with pytest.raises(PolicyError, match="unknown classification"):
        policy.rank("top_secret")


# ---------------------------------------------------------------------------- #
# The four-step resolution rule
# ---------------------------------------------------------------------------- #


def test_within_clearance_is_never_masked(policy):
    assert (
        policy.resolve_masking(column("city", "internal", masking="redact"), "analyst")
        == "none"
    )


def test_role_override_beats_the_column_strategy(policy):
    # email declares `hash`; support overrides it to `partial` so staff can verify
    # a caller without being handed the address.
    assert (
        policy.resolve_masking(
            column("email", "restricted", masking="hash", pii_type="email"), "support"
        )
        == "partial"
    )
    assert (
        policy.resolve_masking(
            column("email", "restricted", masking="hash", pii_type="email"), "analyst"
        )
        == "hash"
    )


def test_column_strategy_applies_without_an_override(policy):
    assert (
        policy.resolve_masking(
            column("date_of_birth", "restricted", masking="generalize"), "analyst"
        )
        == "generalize"
    )


def test_undeclared_strategy_fails_closed(policy):
    """The single most important behaviour in this module.

    A sensitive column with no masking strategy must be redacted, not passed
    through. A governance framework that fails open is worse than none, because
    it is trusted.
    """
    assert policy.resolve_masking(column("mystery", "restricted"), "analyst") == "redact"
    assert (
        policy.resolve_masking(column("mystery", "confidential"), "analyst") == "redact"
    )


def test_unknown_strategy_is_rejected_rather_than_ignored(policy):
    with pytest.raises(PolicyError, match="unknown masking strategy"):
        policy.resolve_masking(
            column("email", "restricted", masking="encrypt_maybe"), "analyst"
        )


def test_tokenize_refuses_to_pretend(policy):
    """Declared but unimplemented. It must raise, not silently hash.

    Substituting a hash for a reversible token would misrepresent the control to
    anyone reading the catalog.
    """
    with pytest.raises(PolicyError, match="deliberately not implemented"):
        policy.resolve_masking(
            column("email", "restricted", masking="tokenize"), "analyst"
        )


# ---------------------------------------------------------------------------- #
# Withholding
# ---------------------------------------------------------------------------- #


def test_marketing_withholds_rather_than_masks(policy):
    assert policy.is_dropped_for_role(column("email", "restricted", "hash"), "marketing")
    assert policy.is_dropped_for_role(column("balance", "confidential"), "marketing")


def test_an_explicit_none_override_survives_the_blanket_drop(policy):
    """Marketing must see consent state -- acting on a stale opt-in is the failure."""
    assert not policy.is_dropped_for_role(column("consent", "confidential"), "marketing")


def test_other_roles_mask_instead_of_dropping(policy):
    assert not policy.is_dropped_for_role(
        column("email", "restricted", "hash"), "analyst"
    )


def test_within_clearance_columns_are_never_dropped(policy):
    assert not policy.is_dropped_for_role(column("tier", "internal"), "marketing")


# ---------------------------------------------------------------------------- #
# Scope
# ---------------------------------------------------------------------------- #


def model(name: str, layer: str) -> Model:
    return Model(
        name=name,
        layer=layer,
        schema="marts",
        description="",
        grain=None,
        kimball_type=None,
        contains_pii=False,
        columns=[],
        depends_on=[],
        materialization="table",
    )


def test_only_marts_get_secure_views(policy):
    assert policy.in_secure_scope(model("dim_customer", "30_marts"))
    assert not policy.in_secure_scope(model("stg_orders", "10_staging"))
    assert not policy.in_secure_scope(model("int_order_fills", "20_intermediate"))


def test_excluded_models_are_skipped(policy):
    assert not policy.in_secure_scope(model("dim_date", "30_marts"))


# ---------------------------------------------------------------------------- #
# Masking SQL selection
# ---------------------------------------------------------------------------- #


def test_generalize_dispatches_on_physical_type_first():
    """Regression test.

    `age_years` is derived from a date of birth and tagged `pii_type:
    date_of_birth`, but it is an INTEGER. Dispatching on the semantic type first
    emitted YEAR(age_years), which fails to bind.
    """
    from governance.generate_secure_views import masking_expression

    policy = Policy(POLICY_DOCUMENT)

    integer_age = column(
        "age_years", "confidential", "generalize", "date_of_birth", "INTEGER"
    )
    assert "mask_generalize_numeric" in masking_expression(
        policy, integer_age, "generalize"
    )

    real_date = column(
        "date_of_birth", "restricted", "generalize", "date_of_birth", "DATE"
    )
    assert "mask_generalize_date" in masking_expression(policy, real_date, "generalize")

    timestamp = column(
        "last_seen_at", "confidential", "generalize", "behavioural", "TIMESTAMP"
    )
    assert "mask_generalize_timestamp" in masking_expression(
        policy, timestamp, "generalize"
    )

    postcode = column("postcode", "confidential", "generalize", "address", "VARCHAR")
    assert "mask_generalize_postcode" in masking_expression(
        policy, postcode, "generalize"
    )


def test_partial_dispatches_on_pii_type():
    from governance.generate_secure_views import masking_expression

    policy = Policy(POLICY_DOCUMENT)
    assert "mask_partial_email" in masking_expression(
        policy, column("email", "restricted", "partial", "email"), "partial"
    )
    assert "mask_partial_phone" in masking_expression(
        policy, column("phone_number", "restricted", "partial", "phone"), "partial"
    )
    assert "mask_partial_generic" in masking_expression(
        policy, column("odd", "restricted", "partial", "other"), "partial"
    )


def test_redact_carries_the_column_type():
    """A typed NULL keeps the view's schema stable; an untyped one does not."""
    from governance.generate_secure_views import masking_expression

    policy = Policy(POLICY_DOCUMENT)
    expression = masking_expression(
        policy, column("dob", "restricted", "redact", "date_of_birth", "DATE"), "redact"
    )
    assert "mask_redact('dob', 'DATE')" in expression


def test_passthrough_emits_the_bare_column():
    from governance.generate_secure_views import masking_expression

    policy = Policy(POLICY_DOCUMENT)
    assert masking_expression(policy, column("city", "confidential"), "none") == "city"


# ---------------------------------------------------------------------------- #
# The real project
# ---------------------------------------------------------------------------- #


def test_real_policy_loads_and_is_internally_consistent():
    """Every role clearance and override strategy in policy.yml must be valid."""
    policy = Policy.load()
    for role_name, role in policy.roles.items():
        assert role["clearance"] in policy.classifications, role_name
        assert "schema" in role, role_name
        for column_name, strategy in (role.get("overrides") or {}).items():
            assert strategy in policy.masking_strategies, (role_name, column_name)


def test_every_classification_has_a_distinct_rank():
    policy = Policy.load()
    ranks = [entry["rank"] for entry in policy.classifications.values()]
    assert len(set(ranks)) == len(ranks)
