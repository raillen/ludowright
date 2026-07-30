"""Versioned contract for the data-driven asset taxonomy."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ludowright.contracts.common import (
    ContractModel,
    DisplayText,
    PositiveRevision,
    ReviewText,
    Slug,
)
from ludowright.domain import AssetFamily

TaxonomyPrefix = Annotated[Slug, Field(max_length=20)]


class AssetSubtypeDefinitionContract(ContractModel):
    """One data-defined subtype within an asset family."""

    id: Slug
    label: DisplayText
    description: ReviewText


class AssetFamilyDefinitionContract(ContractModel):
    """One stable family and its initial subtype catalog."""

    family: AssetFamily
    label: DisplayText
    description: ReviewText
    subtypes: tuple[AssetSubtypeDefinitionContract, ...] = ()

    @model_validator(mode="after")
    def validate_subtypes(self) -> Self:
        subtype_ids = tuple(subtype.id for subtype in self.subtypes)
        if len(subtype_ids) != len(set(subtype_ids)):
            raise ValueError(f"asset taxonomy subtypes must be unique for {self.family.value}")
        if tuple(sorted(subtype_ids)) != subtype_ids:
            raise ValueError(f"asset taxonomy subtypes must be sorted for {self.family.value}")
        return self


class AssetNamingRuleContract(ContractModel):
    """Naming prefix for one stable asset family."""

    family: AssetFamily
    prefix: TaxonomyPrefix


class AssetNamingPolicyContract(ContractModel):
    """Data-defined naming policy for asset identifiers."""

    asset_id_format: Literal["{prefix}-{slug}"] = "{prefix}-{slug}"
    rules: tuple[AssetNamingRuleContract, ...]

    @model_validator(mode="after")
    def validate_rules(self) -> Self:
        families = tuple(rule.family for rule in self.rules)
        prefixes = tuple(rule.prefix for rule in self.rules)
        if len(families) != len(set(families)):
            raise ValueError("asset naming rules must contain one rule per family")
        if len(prefixes) != len(set(prefixes)):
            raise ValueError("asset naming prefixes must be unique")
        if set(families) != set(AssetFamily):
            raise ValueError("asset naming rules must cover every asset family")
        if tuple(sorted(families, key=lambda family: family.value)) != families:
            raise ValueError("asset naming rules must be sorted by family")
        return self


class AssetTaxonomyContract(ContractModel):
    """Complete versioned taxonomy catalog shipped with LudoWright."""

    schema_version: Literal[1] = 1
    kind: Literal["asset-taxonomy"] = "asset-taxonomy"
    version: PositiveRevision
    families: tuple[AssetFamilyDefinitionContract, ...]
    naming_policy: AssetNamingPolicyContract

    @model_validator(mode="after")
    def validate_families(self) -> Self:
        families = tuple(definition.family for definition in self.families)
        if len(families) != len(set(families)):
            raise ValueError("asset taxonomy families must be unique")
        if set(families) != set(AssetFamily):
            raise ValueError("asset taxonomy must cover every asset family")
        if tuple(sorted(families, key=lambda family: family.value)) != families:
            raise ValueError("asset taxonomy families must be sorted by family")
        naming_families = {rule.family for rule in self.naming_policy.rules}
        if naming_families != set(families):
            raise ValueError("asset taxonomy and naming policy families must match")
        return self
