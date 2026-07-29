"""Stable machine-readable contracts for LudoWright CLI responses."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from ludowright.contracts.common import ContractModel, RevisionText

_MAX_JSON_DEPTH = 64
_MAX_JSON_VALUES = 100_000
CommandName = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:[ -][a-z0-9]+)*$",
    ),
]
ErrorMessage = Annotated[str, StringConstraints(min_length=1, max_length=4_000)]


class CliErrorCode(StrEnum):
    """Stable machine-readable categories for command failures."""

    CHECKS_FAILED = "checks-failed"
    INVALID_INPUT = "invalid-input"
    PROJECT_NOT_FOUND = "project-not-found"
    CONFLICT = "conflict"
    CORRUPT_STATE = "corrupt-state"
    BLOCKED = "blocked"
    INTERNAL_ERROR = "internal-error"


class CliMetaContract(ContractModel):
    """Metadata shared by every JSON response."""

    ludowright_version: RevisionText
    output: Literal["json"] = "json"


class CliErrorContract(ContractModel):
    """One stable CLI error with optional JSON-compatible detail."""

    code: CliErrorCode
    message: ErrorMessage
    details: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_details(self) -> Self:
        _validate_json_object(self.details, label="CLI error details")
        return self


class CliResponseContract(ContractModel):
    """Success or failure envelope emitted by commands in JSON mode."""

    schema_version: Literal[1] = 1
    kind: Literal["cli-response"] = "cli-response"
    command: CommandName
    ok: bool
    data: dict[str, object] = Field(default_factory=dict)
    error: CliErrorContract | None = None
    meta: CliMetaContract

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        _validate_json_object(self.data, label="CLI response data")
        if self.ok and self.error is not None:
            raise ValueError("a successful CLI response cannot contain an error")
        if not self.ok and self.error is None:
            raise ValueError("a failed CLI response requires an error")
        return self

    @classmethod
    def success(
        cls,
        *,
        command: str,
        data: dict[str, object],
        ludowright_version: str,
    ) -> Self:
        return cls(
            command=command,
            ok=True,
            data=data,
            error=None,
            meta=CliMetaContract(ludowright_version=ludowright_version),
        )

    @classmethod
    def failure(
        cls,
        *,
        command: str,
        data: dict[str, object],
        error: CliErrorContract,
        ludowright_version: str,
    ) -> Self:
        return cls(
            command=command,
            ok=False,
            data=data,
            error=error,
            meta=CliMetaContract(ludowright_version=ludowright_version),
        )


def _validate_json_object(value: dict[str, object], *, label: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    remaining = [_MAX_JSON_VALUES]
    _validate_json_value(value, depth=0, remaining=remaining, label=label)


def _validate_json_value(
    value: object,
    *,
    depth: int,
    remaining: list[int],
    label: str,
) -> None:
    remaining[0] -= 1
    if remaining[0] < 0:
        raise ValueError(f"{label} cannot exceed {_MAX_JSON_VALUES} values")
    if depth > _MAX_JSON_DEPTH:
        raise ValueError(f"{label} cannot exceed {_MAX_JSON_DEPTH} nesting levels")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{label} cannot contain non-finite numbers")
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_json_value(
                item,
                depth=depth + 1,
                remaining=remaining,
                label=label,
            )
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError(f"{label} keys must be strings")
        for item in value.values():
            _validate_json_value(
                item,
                depth=depth + 1,
                remaining=remaining,
                label=label,
            )
        return
    raise ValueError(f"{label} cannot contain {type(value).__name__} values")
