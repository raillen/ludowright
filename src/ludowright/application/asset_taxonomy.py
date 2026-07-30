"""Data-driven asset taxonomy loading and classification validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib import resources

from pydantic import ValidationError

from ludowright.contracts import (
    AssetFamilyDefinitionContract,
    AssetNamingRuleContract,
    AssetTaxonomyContract,
)
from ludowright.domain import (
    AssetClassification,
    AssetFamily,
    AssetId,
    AssetSubtype,
    InvalidAssetError,
    InvalidIdentifierError,
    validate_slug,
)

_TAXONOMY_RESOURCE = "asset-taxonomy.json"


class AssetTaxonomyError(RuntimeError):
    """Raised when the built-in taxonomy cannot be loaded or validated."""


class AssetTaxonomyValidationError(AssetTaxonomyError):
    """Raised when a classification or asset ID violates the taxonomy policy."""


@dataclass(frozen=True, slots=True)
class AssetTaxonomy:
    """Validated taxonomy snapshot with deterministic classification helpers."""

    contract: AssetTaxonomyContract
    source_digest: str

    def family(self, family: AssetFamily) -> AssetFamilyDefinitionContract:
        """Return the data definition for one stable family."""
        if not isinstance(family, AssetFamily):
            raise AssetTaxonomyValidationError("asset family must be a valid AssetFamily")
        return next(
            definition for definition in self.contract.families if definition.family is family
        )

    def naming_rule(self, family: AssetFamily) -> AssetNamingRuleContract:
        """Return the naming rule for one stable family."""
        if not isinstance(family, AssetFamily):
            raise AssetTaxonomyValidationError("asset family must be a valid AssetFamily")
        return next(rule for rule in self.contract.naming_policy.rules if rule.family is family)

    def supports_subtype(self, family: AssetFamily, subtype: str) -> bool:
        """Return whether a family explicitly declares a subtype."""
        definition = self.family(family)
        return any(candidate.id == subtype for candidate in definition.subtypes)

    def validate_classification(
        self,
        family: AssetFamily,
        subtype: AssetSubtype | str | None = None,
    ) -> AssetClassification:
        """Validate a family/subtype pair and return its domain classification."""
        if not isinstance(family, AssetFamily):
            raise AssetTaxonomyValidationError("asset family must be a valid AssetFamily")
        subtype_value = _subtype_value(subtype)
        try:
            classification = AssetClassification(
                family=family,
                subtype=AssetSubtype(subtype_value) if subtype_value is not None else None,
            )
        except (InvalidAssetError, InvalidIdentifierError) as error:
            raise AssetTaxonomyValidationError(str(error)) from error
        if subtype_value is not None and not self.supports_subtype(family, subtype_value):
            raise AssetTaxonomyValidationError(
                f"asset subtype {subtype_value!r} is not declared for {family.value!r}"
            )
        return classification

    def validate_asset_id(self, family: AssetFamily, asset_id: AssetId | str) -> AssetId:
        """Validate the family-specific prefix of an asset identifier."""
        try:
            canonical_id = asset_id if isinstance(asset_id, AssetId) else AssetId(asset_id)
        except (InvalidIdentifierError, TypeError) as error:
            raise AssetTaxonomyValidationError(str(error)) from error
        expected_prefix = f"{self.naming_rule(family).prefix}-"
        if not canonical_id.value.startswith(expected_prefix):
            raise AssetTaxonomyValidationError(
                f"asset ID {canonical_id.value!r} must start with {expected_prefix!r}"
            )
        try:
            validate_slug(canonical_id.value[len(expected_prefix) :])
        except InvalidIdentifierError as error:
            raise AssetTaxonomyValidationError(
                f"asset ID {canonical_id.value!r} has an invalid family slug"
            ) from error
        return canonical_id


def load_asset_taxonomy() -> AssetTaxonomy:
    """Load and validate the packaged taxonomy data deterministically."""
    try:
        payload = (
            resources.files("ludowright.taxonomy_data").joinpath(_TAXONOMY_RESOURCE).read_bytes()
        )
        value = json.loads(payload)
        contract = AssetTaxonomyContract.model_validate(value)
    except (OSError, TypeError, json.JSONDecodeError, ValidationError) as error:
        raise AssetTaxonomyError("packaged asset taxonomy is invalid") from error
    return AssetTaxonomy(contract=contract, source_digest=hashlib.sha256(payload).hexdigest())


def _subtype_value(subtype: AssetSubtype | str | None) -> str | None:
    if subtype is None:
        return None
    if isinstance(subtype, AssetSubtype):
        return str(subtype)
    if isinstance(subtype, str):
        return subtype
    raise AssetTaxonomyValidationError("asset subtype must be an AssetSubtype, string, or None")
