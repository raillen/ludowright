"""Shared Pydantic primitives for published LudoWright contracts."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Slug = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]
DisplayText = Annotated[str, StringConstraints(min_length=1, max_length=120)]
ReviewText = Annotated[str, StringConstraints(min_length=1, max_length=4_000)]
RevisionText = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:+-]*$",
    ),
]
Sha256Text = Annotated[
    str,
    StringConstraints(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"),
]
EngineVersionText = Annotated[str, StringConstraints(min_length=1, max_length=64)]
HttpsUriText = Annotated[
    str,
    StringConstraints(min_length=9, max_length=2_048, pattern=r"^https://"),
]
PositiveRevision = Annotated[int, Field(ge=1, le=2_147_483_647)]


class ContractModel(BaseModel):
    """Strict immutable base for persisted and published contract models."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)
