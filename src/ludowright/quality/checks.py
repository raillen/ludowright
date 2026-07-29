"""Deterministic execution of repository quality checks."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

Executor = Callable[[tuple[str, ...]], int]


@dataclass(frozen=True, slots=True)
class CheckSpec:
    """A named command that participates in a quality gate."""

    name: str
    command: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CheckResult:
    """The stable result of executing one quality check."""

    name: str
    command: tuple[str, ...]
    exit_code: int
    skipped: bool = False

    @property
    def passed(self) -> bool:
        """Return whether the check completed successfully."""
        return self.exit_code == 0

    def to_dict(self) -> dict[str, object]:
        """Return a machine-readable representation."""
        return {
            "command": list(self.command),
            "exit_code": self.exit_code,
            "name": self.name,
            "passed": self.passed,
            "skipped": self.skipped,
        }


QUALITY_CHECKS: tuple[CheckSpec, ...] = (
    CheckSpec("pre-commit", ("uv", "run", "pre-commit", "run", "--all-files")),
    CheckSpec("tests", ("uv", "run", "pytest")),
    CheckSpec(
        "schema-publication",
        ("uv", "run", "python", "-m", "ludowright.contracts", "check"),
    ),
    CheckSpec("documentation", ("uv", "run", "mkdocs", "build", "--strict", "--clean")),
    CheckSpec("dependency-audit", ("uv", "run", "pip-audit")),
)

RELEASE_CHECKS: tuple[CheckSpec, ...] = (
    *QUALITY_CHECKS,
    CheckSpec("package-build", ("uv", "build")),
)


def _execute(command: tuple[str, ...]) -> int:
    completed = subprocess.run(command, check=False)
    return completed.returncode


def run_checks(
    checks: Sequence[CheckSpec],
    *,
    dry_run: bool = False,
    executor: Executor | None = None,
) -> tuple[CheckResult, ...]:
    """Execute checks in order and preserve a stable result for each one."""
    execute = executor or _execute
    results: list[CheckResult] = []

    for check in checks:
        if dry_run:
            results.append(
                CheckResult(
                    name=check.name,
                    command=check.command,
                    exit_code=0,
                    skipped=True,
                )
            )
            continue

        results.append(
            CheckResult(
                name=check.name,
                command=check.command,
                exit_code=execute(check.command),
            )
        )

    return tuple(results)
