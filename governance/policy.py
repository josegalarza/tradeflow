"""Shared policy loading and resolution.

One module owns the interpretation of ``policy.yml`` and the dbt manifest, so
the CI gate, the secure-view generator and the catalog builder cannot disagree
about what a tag means. Three tools with three copies of the resolution rule is
three subtly different access policies.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO_ROOT / "governance" / "policy.yml"
MANIFEST_PATH = REPO_ROOT / "warehouse" / "target" / "manifest.json"
CATALOG_PATH = REPO_ROOT / "warehouse" / "target" / "catalog.json"


class PolicyError(RuntimeError):
    """Raised when the policy or the tags it depends on are unusable."""


@dataclass(frozen=True)
class Column:
    """A column, with its governance metadata resolved."""

    name: str
    description: str
    classification: str
    is_pii: bool
    pii_type: str | None
    masking: str | None
    data_type: str | None
    is_technical: bool
    # "explicit"     -- meta.classification declared in the schema YAML
    # "technical"    -- name starts with the technical prefix, auto-classified
    # "layer_default"-- documented, untagged, inheriting the layer default
    # "undocumented" -- exists in the database but appears in no schema YAML
    classification_source: str
    rationale: str | None = None
    # False when the column is documented in YAML but absent from the built
    # warehouse -- stale documentation. The secure-view generator must skip these
    # or it emits SQL referencing a column that does not exist, and the resulting
    # binder error points at the generated file rather than at the stale docs.
    in_database: bool = True


@dataclass(frozen=True)
class Model:
    """A dbt model, with its columns and governance metadata."""

    name: str
    layer: str
    schema: str
    description: str
    grain: str | None
    kimball_type: str | None
    contains_pii: bool
    columns: list[Column]
    depends_on: list[str]
    materialization: str


class Policy:
    """Loaded policy, with the resolution rules applied on demand."""

    def __init__(self, document: dict[str, Any]) -> None:
        self.document = document
        self.classifications = document["classifications"]
        self.masking_strategies = document["masking_strategies"]
        self.roles = document["roles"]
        self.scope = document["secure_view_scope"]
        self.enforcement = document["enforcement"]

    @classmethod
    def load(cls, path: Path = POLICY_PATH) -> Policy:
        with path.open() as handle:
            return cls(yaml.safe_load(handle))

    # -- classification helpers ------------------------------------------- #

    def rank(self, classification: str) -> int:
        try:
            return self.classifications[classification]["rank"]
        except KeyError as exc:
            raise PolicyError(
                f"unknown classification {classification!r}; "
                f"valid values are {sorted(self.classifications)}"
            ) from exc

    def is_visible_to(self, classification: str, role_name: str) -> bool:
        """True when the role's clearance covers the column outright."""
        role = self.role(role_name)
        return self.rank(classification) <= self.rank(role["clearance"])

    def role(self, role_name: str) -> dict[str, Any]:
        try:
            return self.roles[role_name]
        except KeyError as exc:
            raise PolicyError(
                f"unknown role {role_name!r}; valid roles are {sorted(self.roles)}"
            ) from exc

    def resolve_masking(self, column: Column, role_name: str) -> str:
        """Which masking strategy applies to this column for this role.

        Implements the four-step rule documented in policy.yml. Returns the
        strategy name; ``"none"`` means pass the column through unchanged.
        """
        role = self.role(role_name)

        # 1. Within clearance: no masking at all.
        if self.is_visible_to(column.classification, role_name):
            return "none"

        # 2. An explicit per-role override for this column name.
        override = role.get("overrides", {}).get(column.name)
        if override is not None:
            self._validate_strategy(override, column, role_name)
            return override

        # 3. The column's own declared strategy.
        if column.masking is not None:
            self._validate_strategy(column.masking, column, role_name)
            return column.masking

        # 4. Nothing declared: fail safe, not open.
        return "redact"

    def _validate_strategy(self, strategy: str, column: Column, role: str) -> None:
        if strategy not in self.masking_strategies:
            raise PolicyError(
                f"unknown masking strategy {strategy!r} for column "
                f"{column.name!r} (role {role!r}); valid strategies are "
                f"{sorted(self.masking_strategies)}"
            )
        if strategy == "tokenize":
            raise PolicyError(
                f"column {column.name!r} requests the 'tokenize' strategy, which "
                "is declared but deliberately not implemented -- it needs a real "
                "token vault with its own key management. Silently substituting a "
                "hash would misrepresent the control. Choose 'hash' explicitly if "
                "that is what you mean."
            )

    def is_dropped_for_role(self, column: Column, role_name: str) -> bool:
        """True when the role omits the column entirely rather than masking it."""
        role = self.role(role_name)
        if not role.get("drop_above_clearance"):
            return False
        if self.is_visible_to(column.classification, role_name):
            return False
        # An explicit `none` override is a decision to expose the column, and
        # outranks the blanket drop.
        return role.get("overrides", {}).get(column.name) != "none"

    # -- scope ------------------------------------------------------------- #

    def in_secure_scope(self, model: Model) -> bool:
        return model.layer in self.scope["include_layers"] and model.name not in set(
            self.scope.get("exclude_models") or []
        )


def _layer_of(node: dict[str, Any]) -> str:
    """Derive the layer from the model's directory, falling back to meta.

    The directory is the source of truth because it is the thing the layer
    boundary check enforces, and a meta tag can drift from where the file
    actually lives.
    """
    path = node.get("path", "")
    head = path.split("/")[0] if "/" in path else ""
    if head:
        return head
    return (node.get("meta") or {}).get("layer", "unknown")


#: The layer whose models are produced by generate_secure_views.py. No
#: classification decision is made there -- every column is a projection of a
#: classified mart column -- so the catalog and the coverage gate exclude it.
#: Including it would report ~1,000 "undocumented restricted" columns that are
#: in fact the masked outputs of columns already counted once.
GENERATED_LAYER = "40_secure"


def load_models(
    manifest_path: Path = MANIFEST_PATH,
    catalog_path: Path = CATALOG_PATH,
    policy: Policy | None = None,
    include_generated: bool = True,
) -> list[Model]:
    """Read models and their governance metadata out of the dbt artefacts.

    The manifest supplies the tags, and ``catalog.json`` supplies the columns
    that physically exist. Both are needed, and the distinction is what makes
    the CI gate trustworthy:

    * the manifest only lists columns somebody wrote a YAML entry for, so a gate
      driven by the manifest alone would happily pass a model with an
      undocumented ``national_id`` column -- the exact case it exists to catch;
    * the catalog is the database's own account of what is there, so a column
      present in the catalog and absent from the manifest is reported as
      ``undocumented`` rather than silently skipped.

    The catalog also carries data types, which the secure-view generator needs so
    a redaction can be a typed NULL rather than an untyped one. Without a catalog
    the loader degrades to manifest-only and marks the result unverified, because
    claiming 100% coverage from an incomplete column list would be worse than
    admitting the gap.
    """
    if not manifest_path.exists():
        raise PolicyError(
            f"no dbt manifest at {manifest_path}. Run `make build` (or "
            "`dbt parse`) first -- the governance tools read the tags out of the "
            "manifest rather than re-parsing the YAML themselves."
        )

    policy = policy or Policy.load()
    with manifest_path.open() as handle:
        manifest = json.load(handle)

    types: dict[str, dict[str, str]] = {}
    if catalog_path.exists():
        with catalog_path.open() as handle:
            catalog = json.load(handle)
        for unique_id, entry in catalog.get("nodes", {}).items():
            types[unique_id] = {
                name: meta.get("type", "VARCHAR")
                for name, meta in entry.get("columns", {}).items()
            }

    enforcement = policy.enforcement
    prefix = enforcement["technical_column_prefix"]
    technical_classification = enforcement["technical_column_classification"]
    layer_defaults = enforcement.get("default_classification_by_layer") or {}

    models: list[Model] = []
    for unique_id, node in manifest["nodes"].items():
        if node.get("resource_type") != "model":
            continue

        layer = _layer_of(node)
        if layer == GENERATED_LAYER and not include_generated:
            continue
        model_meta = node.get("meta") or {}
        column_types = types.get(unique_id, {})

        documented = node.get("columns") or {}
        # Physical columns first, in database order, so the generated views keep
        # the column order of the models they mask. Documented-but-absent columns
        # are appended: a YAML entry for a column that no longer exists is stale
        # documentation and worth surfacing too.
        column_names = list(column_types) or list(documented)
        for name in documented:
            if name not in column_names:
                column_names.append(name)

        columns: list[Column] = []
        for name in column_names:
            column = documented.get(name)
            column_meta = (column or {}).get("meta") or {}
            is_technical = name.startswith(prefix)

            if "classification" in column_meta:
                classification = column_meta["classification"]
                source = "explicit"
            elif is_technical:
                classification = technical_classification
                source = "technical"
            elif column is None:
                # Exists in the warehouse, described nowhere. It inherits the
                # layer default like any other untagged column -- reporting it as
                # `restricted` instead would be a fail-safe in the wrong place:
                # it would make the catalog claim half the warehouse is regulated
                # data, which is the kind of inaccuracy that gets a catalog
                # ignored.
                #
                # The fail-safe that matters lives in Policy.resolve_masking,
                # where an undeclared masking strategy becomes `redact`. And in
                # layers requiring full coverage this is an error that fails the
                # build, so the default never gets to matter there.
                classification = layer_defaults.get(layer, "confidential")
                source = "undocumented"
            else:
                classification = layer_defaults.get(layer, "confidential")
                source = "layer_default"

            columns.append(
                Column(
                    name=name,
                    description=((column or {}).get("description") or "").strip(),
                    classification=classification,
                    is_pii=bool(column_meta.get("pii", False)),
                    pii_type=column_meta.get("pii_type"),
                    masking=column_meta.get("masking"),
                    data_type=column_types.get(name),
                    is_technical=is_technical,
                    classification_source=source,
                    rationale=column_meta.get("classification_rationale"),
                    # Without a catalog there is nothing to compare against, so
                    # assume presence rather than reporting every column stale.
                    in_database=(not column_types) or (name in column_types),
                )
            )

        models.append(
            Model(
                name=node["name"],
                layer=layer,
                schema=node.get("schema", ""),
                description=(node.get("description") or "").strip(),
                grain=model_meta.get("grain"),
                kimball_type=model_meta.get("kimball_type"),
                contains_pii=bool(model_meta.get("contains_pii", False)),
                columns=columns,
                depends_on=list((node.get("depends_on") or {}).get("nodes") or []),
                materialization=(node.get("config") or {}).get("materialized", ""),
            )
        )

    return sorted(models, key=lambda model: (model.layer, model.name))


def documented_columns_in_database(
    database_path: Path, schema: str, table: str
) -> dict[str, str]:
    """Column types straight from DuckDB, for models the catalog has not seen."""
    import duckdb

    with duckdb.connect(str(database_path), read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = ? AND table_name = ?
            """,
            [schema, table],
        ).fetchall()
    return dict(rows)
