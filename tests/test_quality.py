"""Tests for deterministic quality-check execution."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from ludowright.quality import CheckSpec, run_checks


@given(st.lists(st.integers(min_value=0, max_value=5), min_size=1, max_size=8))
def test_run_checks_preserves_order_and_exit_codes(exit_codes: list[int]) -> None:
    checks = tuple(
        CheckSpec(name=f"check-{index}", command=("tool", str(index)))
        for index in range(len(exit_codes))
    )
    remaining_codes = iter(exit_codes)

    results = run_checks(checks, executor=lambda _command: next(remaining_codes))

    assert [result.name for result in results] == [check.name for check in checks]
    assert [result.exit_code for result in results] == exit_codes
    assert [result.passed for result in results] == [code == 0 for code in exit_codes]
    assert all(result.skipped is False for result in results)


def test_dry_run_skips_executor_and_preserves_commands() -> None:
    checks = (CheckSpec(name="example", command=("example", "--check")),)

    def unexpected_executor(_command: tuple[str, ...]) -> int:
        raise AssertionError("executor must not run during a dry run")

    results = run_checks(checks, dry_run=True, executor=unexpected_executor)

    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].skipped is True
    assert results[0].command == checks[0].command
    assert results[0].to_dict() == {
        "command": ["example", "--check"],
        "exit_code": 0,
        "name": "example",
        "passed": True,
        "skipped": True,
    }
