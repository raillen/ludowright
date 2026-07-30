"""Command-line interface for LudoWright."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from ludowright import __version__
from ludowright.application import GovernanceService
from ludowright.cli.diagnostics import collect_diagnostics, render_diagnostics
from ludowright.cli.quality import quality_app
from ludowright.cli.runtime import (
    CliSettings,
    canonical_json,
    run_command,
)
from ludowright.contracts.cli import CliResponseContract
from ludowright.contracts.governance import ApprovalSubjectKind
from ludowright.domain import ApprovalStatus, DecisionStatus

app = typer.Typer(
    name="ludowright",
    help="Plan, document, visualize, validate, and package game projects.",
    no_args_is_help=True,
    invoke_without_command=True,
    pretty_exceptions_enable=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(quality_app, name="quality")
decision_app = typer.Typer(
    name="decision",
    help="Record and review immutable project decisions.",
    no_args_is_help=True,
)
approval_app = typer.Typer(
    name="approval",
    help="Request and record revision-bound approvals.",
    no_args_is_help=True,
)
app.add_typer(decision_app, name="decision")
app.add_typer(approval_app, name="approval")
_governance = GovernanceService()


@app.callback()
def root(
    context: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the installed LudoWright version and exit.",
            is_eager=True,
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Return stable machine-readable responses for the selected command.",
        ),
    ] = False,
    no_color: Annotated[
        bool,
        typer.Option("--no-color", help="Disable colored human-readable output."),
    ] = False,
) -> None:
    """Run the LudoWright command-line interface."""
    settings = CliSettings(json_output=json_output, no_color=no_color)
    context.obj = settings
    if version:
        if json_output:
            response = CliResponseContract.success(
                command="version",
                data={"version": __version__},
                ludowright_version=__version__,
            )
            typer.echo(canonical_json(response))
        else:
            typer.echo(__version__)
        raise typer.Exit()


@app.command()
def status(
    context: typer.Context,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Show the current framework bootstrap status."""

    def action() -> dict[str, object]:
        return {
            "status": "foundation",
            "version": __version__,
        }

    def render(console: Console, data: dict[str, object]) -> None:
        console.print("[bold]LudoWright[/bold] is in the foundation phase.")
        console.print(f"Version: {data['version']}")

    run_command(
        context=context,
        command="status",
        local_json=json_output,
        action=action,
        render_human=render,
    )


@app.command()
def diagnostics(
    context: typer.Context,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Inspect the runtime environment and nearest project without changing files."""
    run_command(
        context=context,
        command="diagnostics",
        local_json=json_output,
        action=collect_diagnostics,
        render_human=render_diagnostics,
    )


@decision_app.command("record")
def decision_record(
    context: typer.Context,
    path: Annotated[Path, typer.Argument(help="Project directory or a path inside it.")],
    decision_id: Annotated[str, typer.Option("--id", help="Canonical decision ID.")],
    title: Annotated[str, typer.Option("--title", help="Human-readable decision title.")],
    note: Annotated[str | None, typer.Option("--note", help="Initial rationale or note.")] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Record a new proposed decision."""
    run_command(
        context=context,
        command="decision record",
        local_json=json_output,
        action=lambda: _governance.record_decision(
            path,
            decision_id=decision_id,
            title=title,
            note=note,
        ),
        render_human=lambda console, data: _render_record(console, "Decision", data),
    )


@decision_app.command("list")
def decision_list(
    context: typer.Context,
    path: Annotated[Path, typer.Argument(help="Project directory or a path inside it.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """List decisions in stable ID order."""
    run_command(
        context=context,
        command="decision list",
        local_json=json_output,
        action=lambda: _governance.list_decisions(path),
        render_human=lambda console, data: _render_list(console, "Decisions", data, "decisions"),
    )


@decision_app.command("inspect")
def decision_inspect(
    context: typer.Context,
    path: Annotated[Path, typer.Argument(help="Project directory or a path inside it.")],
    decision_id: Annotated[str, typer.Argument(help="Canonical decision ID.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Inspect one decision and its complete immutable history."""
    run_command(
        context=context,
        command="decision inspect",
        local_json=json_output,
        action=lambda: _governance.inspect_decision(path, decision_id=decision_id),
        render_human=lambda console, data: _render_inspect(console, "Decision", data),
    )


@decision_app.command("transition")
def decision_transition(
    context: typer.Context,
    path: Annotated[Path, typer.Argument(help="Project directory or a path inside it.")],
    decision_id: Annotated[str, typer.Argument(help="Canonical decision ID.")],
    status: Annotated[DecisionStatus, typer.Option("--status", help="Target decision status.")],
    note: Annotated[str | None, typer.Option("--note", help="Transition rationale.")] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Append an allowed decision state transition."""
    run_command(
        context=context,
        command="decision transition",
        local_json=json_output,
        action=lambda: _governance.transition_decision(
            path,
            decision_id=decision_id,
            status=status,
            note=note,
        ),
        render_human=lambda console, data: _render_record(console, "Decision", data),
    )


@decision_app.command("supersede")
def decision_supersede(
    context: typer.Context,
    path: Annotated[Path, typer.Argument(help="Project directory or a path inside it.")],
    decision_id: Annotated[str, typer.Argument(help="Accepted decision to supersede.")],
    replacement_id: Annotated[
        str,
        typer.Option("--replacement-id", help="Existing replacement decision ID."),
    ],
    note: Annotated[str | None, typer.Option("--note", help="Supersession rationale.")] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Supersede an accepted decision with another recorded decision."""
    run_command(
        context=context,
        command="decision supersede",
        local_json=json_output,
        action=lambda: _governance.supersede_decision(
            path,
            decision_id=decision_id,
            replacement_id=replacement_id,
            note=note,
        ),
        render_human=lambda console, data: _render_record(console, "Decision", data),
    )


@approval_app.command("request")
def approval_request(
    context: typer.Context,
    path: Annotated[Path, typer.Argument(help="Project directory or a path inside it.")],
    approval_id: Annotated[str, typer.Option("--id", help="Canonical approval ID.")],
    subject_kind: Annotated[
        ApprovalSubjectKind,
        typer.Option("--subject-kind", help="Typed kind of the reviewed subject."),
    ],
    subject_id: Annotated[str, typer.Option("--subject-id", help="Reviewed entity ID.")],
    revision: Annotated[str, typer.Option("--revision", help="Immutable subject fingerprint.")],
    label: Annotated[str | None, typer.Option("--label", help="Optional subject label.")] = None,
    note: Annotated[str | None, typer.Option("--note", help="Initial review note.")] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Request approval for one immutable subject revision."""
    run_command(
        context=context,
        command="approval request",
        local_json=json_output,
        action=lambda: _governance.request_approval(
            path,
            approval_id=approval_id,
            subject_kind=subject_kind.value,
            subject_id=subject_id,
            revision=revision,
            label=label,
            note=note,
        ),
        render_human=lambda console, data: _render_record(console, "Approval", data),
    )


@approval_app.command("list")
def approval_list(
    context: typer.Context,
    path: Annotated[Path, typer.Argument(help="Project directory or a path inside it.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """List approval requests in stable ID order."""
    run_command(
        context=context,
        command="approval list",
        local_json=json_output,
        action=lambda: _governance.list_approvals(path),
        render_human=lambda console, data: _render_list(console, "Approvals", data, "approvals"),
    )


@approval_app.command("inspect")
def approval_inspect(
    context: typer.Context,
    path: Annotated[Path, typer.Argument(help="Project directory or a path inside it.")],
    approval_id: Annotated[str, typer.Argument(help="Canonical approval ID.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Inspect one approval and its complete immutable history."""
    run_command(
        context=context,
        command="approval inspect",
        local_json=json_output,
        action=lambda: _governance.inspect_approval(path, approval_id=approval_id),
        render_human=lambda console, data: _render_inspect(console, "Approval", data),
    )


@approval_app.command("transition")
def approval_transition(
    context: typer.Context,
    path: Annotated[Path, typer.Argument(help="Project directory or a path inside it.")],
    approval_id: Annotated[str, typer.Argument(help="Canonical approval ID.")],
    status: Annotated[ApprovalStatus, typer.Option("--status", help="Target approval status.")],
    note: Annotated[str | None, typer.Option("--note", help="Transition rationale.")] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Append an allowed approval state transition."""
    run_command(
        context=context,
        command="approval transition",
        local_json=json_output,
        action=lambda: _governance.transition_approval(
            path,
            approval_id=approval_id,
            status=status,
            note=note,
        ),
        render_human=lambda console, data: _render_record(console, "Approval", data),
    )


@approval_app.command("supersede")
def approval_supersede(
    context: typer.Context,
    path: Annotated[Path, typer.Argument(help="Project directory or a path inside it.")],
    approval_id: Annotated[str, typer.Argument(help="Approved request to supersede.")],
    replacement_id: Annotated[
        str,
        typer.Option("--replacement-id", help="Existing replacement approval ID."),
    ],
    note: Annotated[str | None, typer.Option("--note", help="Supersession rationale.")] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Supersede an approved request with another approval request."""
    run_command(
        context=context,
        command="approval supersede",
        local_json=json_output,
        action=lambda: _governance.supersede_approval(
            path,
            approval_id=approval_id,
            replacement_id=replacement_id,
            note=note,
        ),
        render_human=lambda console, data: _render_record(console, "Approval", data),
    )


def _render_record(console: Console, label: str, data: dict[str, object]) -> None:
    console.print(f"[bold green]{label} updated[/bold green]")
    console.print(f"ID: {data['id']}")
    console.print(f"Status: {data['status']}")
    console.print(f"History entries: {data['history_length']}")
    console.print(f"Path: {data['path']}")
    if data.get("event_sequence") is not None:
        console.print(f"Audit event: {data['event_sequence']}")


def _render_list(
    console: Console,
    title: str,
    data: dict[str, object],
    key: str,
) -> None:
    console.print(f"[bold]{title}[/bold]")
    table = Table("ID", "Status", "History", "Path")
    entries = data[key]
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict):
                table.add_row(
                    str(entry.get("id", "")),
                    str(entry.get("status", "")),
                    str(entry.get("history_length", "")),
                    str(entry.get("path", "")),
                )
    console.print(table)


def _render_inspect(console: Console, label: str, data: dict[str, object]) -> None:
    console.print(f"[bold]{label}[/bold]")
    console.print(f"Path: {data['path']}")
    record_key = label.lower()
    record = data.get(record_key)
    if isinstance(record, dict):
        console.print(f"ID: {record.get('id', '')}")
        history = record.get("history", [])
        if isinstance(history, list):
            for revision in history:
                if isinstance(revision, dict):
                    console.print(
                        f"  {revision.get('sequence', '?')}: {revision.get('status', '?')}"
                    )


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
