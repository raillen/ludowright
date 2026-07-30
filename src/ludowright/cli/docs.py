"""Human and JSON presentation for documentation workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown

from ludowright.application import DocumentationAuditError, DocumentationAuditor
from ludowright.cli.runtime import CliExitCode, CliFailure, run_command
from ludowright.contracts import CliErrorCode

docs_app = typer.Typer(
    name="docs",
    help="Inspect and validate repository documentation.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


@docs_app.command("audit")
def audit_documentation(
    context: typer.Context,
    root: Annotated[
        Path,
        typer.Argument(help="Repository root containing the documentation tree."),
    ] = Path("."),
    metadata: Annotated[
        str,
        typer.Option("--metadata", help="Repository-relative ATLAS metadata JSON path."),
    ] = "docs/atlas.json",
    policy: Annotated[
        str,
        typer.Option("--policy", help="Repository-relative audit policy JSON path."),
    ] = "docs/audit-policy.json",
    docs_directory: Annotated[
        str,
        typer.Option("--docs-directory", help="Repository-relative Markdown directory."),
    ] = "docs",
    check: Annotated[
        bool,
        typer.Option("--check", help="Fail when the documentation audit is invalid."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Audit canonical topics, duplicate sources, claims, and stale references."""

    def action() -> dict[str, object]:
        try:
            audit = DocumentationAuditor(
                root,
                docs_directory=docs_directory,
                metadata_path=metadata,
                policy_path=policy,
            ).generate()
        except DocumentationAuditError as error:
            raise CliFailure(
                code=CliErrorCode.CORRUPT_STATE,
                message=str(error),
                exit_code=CliExitCode.CORRUPT_STATE,
            ) from error

        data = audit.report.model_dump(mode="json")
        data.update({"markdown": audit.markdown, "valid": audit.valid})
        if check and not audit.valid:
            raise CliFailure(
                code=CliErrorCode.CHECKS_FAILED,
                message="Documentation audit failed.",
                exit_code=CliExitCode.CHECKS_FAILED,
                details={
                    "broken_links": len(audit.report.broken_links),
                    "findings": len(audit.report.findings),
                    "orphan_documents": len(audit.report.orphan_documents),
                },
                data=data,
            )
        return data

    run_command(
        context=context,
        command="docs audit",
        local_json=json_output,
        action=action,
        render_human=_render_human,
    )


def _render_human(console: Console, data: dict[str, object]) -> None:
    console.print("[bold]Documentation Audit[/bold]")
    console.print(f"Broken links: {_count(data.get('broken_links'))}")
    console.print(f"Orphan documents: {_count(data.get('orphan_documents'))}")
    console.print(f"Policy findings: {_count(data.get('findings'))}")
    if data["valid"]:
        console.print("[green]Documentation audit: valid[/green]")
    else:
        console.print("[bold red]Documentation audit: invalid[/bold red]")
    console.print(Markdown(str(data["markdown"])))


def _count(value: object) -> int:
    return len(value) if isinstance(value, list) else 0
