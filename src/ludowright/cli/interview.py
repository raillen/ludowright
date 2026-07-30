"""Human and JSON presentation for resumable interview commands."""

from __future__ import annotations

import json
from collections.abc import Callable
from json import JSONDecodeError
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from ludowright.application.interviews import (
    InterviewApplicationError,
    InterviewService,
    InterviewView,
)
from ludowright.cli.runtime import (
    CliExitCode,
    CliFailure,
    run_command,
)
from ludowright.contracts.cli import CliErrorCode
from ludowright.contracts.interviews import (
    InterviewBlockedQuestionContract,
    InterviewInteractionContract,
    InterviewProgressContract,
    InterviewQuestionViewContract,
    QuestionOptionContract,
)
from ludowright.domain import (
    AnswerSource,
    InterviewSessionId,
    QuestionId,
)
from ludowright.infrastructure import ProjectFilesystem, RepositoryPath

interview_app = typer.Typer(
    name="interview",
    help="Run and resume a schema-driven project interview.",
    no_args_is_help=True,
)


@interview_app.command("next")
def next_question(
    context: typer.Context,
    project: Annotated[Path, typer.Argument(help="Project directory or a path below it.")] = Path(
        "."
    ),
    questionnaire: Annotated[
        str,
        typer.Option("--questionnaire", "-q", help="Project-relative questionnaire JSON path."),
    ] = ".ludowright/questionnaire.json",
    session: Annotated[
        str,
        typer.Option("--session", "-s", help="Stable resumable interview session ID."),
    ] = "default",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Show the next actionable question without changing the session."""
    _run(
        context=context,
        command="interview next",
        project=project,
        questionnaire=questionnaire,
        session=session,
        local_json=json_output,
        operation=lambda service: service.next_question(),
    )


@interview_app.command("answer")
def answer_question(
    context: typer.Context,
    question_id: Annotated[str, typer.Argument(help="Question ID to answer.")],
    value: Annotated[
        str,
        typer.Option("--value", "-v", help="Answer value; JSON literals are accepted."),
    ],
    project: Annotated[Path, typer.Argument(help="Project directory or a path below it.")] = Path(
        "."
    ),
    questionnaire: Annotated[
        str,
        typer.Option("--questionnaire", "-q", help="Project-relative questionnaire JSON path."),
    ] = ".ludowright/questionnaire.json",
    session: Annotated[
        str,
        typer.Option("--session", "-s", help="Stable resumable interview session ID."),
    ] = "default",
    source: Annotated[
        AnswerSource,
        typer.Option("--source", help="Provenance source for the answer."),
    ] = AnswerSource.HUMAN,
    actor: Annotated[
        str | None,
        typer.Option("--actor", help="Optional provenance actor."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Record one typed answer and show the resulting progress."""
    parsed_value = _parse_answer(value)
    _run(
        context=context,
        command="interview answer",
        project=project,
        questionnaire=questionnaire,
        session=session,
        local_json=json_output,
        operation=lambda service: service.answer(
            QuestionId(question_id), parsed_value, source=source, actor=actor
        ),
    )


@interview_app.command("skip")
def skip_question(
    context: typer.Context,
    question_id: Annotated[str, typer.Argument(help="Optional question ID to skip.")],
    project: Annotated[Path, typer.Argument(help="Project directory or a path below it.")] = Path(
        "."
    ),
    questionnaire: Annotated[
        str,
        typer.Option("--questionnaire", "-q", help="Project-relative questionnaire JSON path."),
    ] = ".ludowright/questionnaire.json",
    session: Annotated[
        str,
        typer.Option("--session", "-s", help="Stable resumable interview session ID."),
    ] = "default",
    actor: Annotated[str | None, typer.Option("--actor")] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Skip an optional question; required questions cannot be skipped."""
    _run(
        context=context,
        command="interview skip",
        project=project,
        questionnaire=questionnaire,
        session=session,
        local_json=json_output,
        operation=lambda service: service.skip(QuestionId(question_id), actor=actor),
    )


@interview_app.command("defer")
def defer_question(
    context: typer.Context,
    question_id: Annotated[str, typer.Argument(help="Question ID to defer.")],
    project: Annotated[Path, typer.Argument(help="Project directory or a path below it.")] = Path(
        "."
    ),
    questionnaire: Annotated[
        str,
        typer.Option("--questionnaire", "-q", help="Project-relative questionnaire JSON path."),
    ] = ".ludowright/questionnaire.json",
    session: Annotated[
        str,
        typer.Option("--session", "-s", help="Stable resumable interview session ID."),
    ] = "default",
    actor: Annotated[str | None, typer.Option("--actor")] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Return a stable machine-readable response."),
    ] = False,
) -> None:
    """Defer a question and keep required work incomplete."""
    _run(
        context=context,
        command="interview defer",
        project=project,
        questionnaire=questionnaire,
        session=session,
        local_json=json_output,
        operation=lambda service: service.defer(QuestionId(question_id), actor=actor),
    )


def _run(
    *,
    context: typer.Context,
    command: str,
    project: Path,
    questionnaire: str,
    session: str,
    local_json: bool,
    operation: Callable[[InterviewService], InterviewView],
) -> None:
    def action() -> dict[str, object]:
        try:
            service = InterviewService(
                ProjectFilesystem.discover(project),
                RepositoryPath.parse(questionnaire),
                InterviewSessionId(session),
            )
            view = operation(service)
            return _interaction_data(view)
        except InterviewApplicationError as error:
            raise CliFailure(
                code=CliErrorCode.CORRUPT_STATE,
                message=str(error),
                exit_code=CliExitCode.CORRUPT_STATE,
            ) from error

    run_command(
        context=context,
        command=command,
        local_json=local_json,
        action=action,
        render_human=_render_human,
    )


def _interaction_data(view: InterviewView) -> dict[str, object]:
    progress = view.progress
    question = (
        InterviewQuestionViewContract(
            id=view.question.id.value,
            prompt=view.question.prompt,
            type=view.question.type,
            required=view.question.required,
            options=tuple(
                QuestionOptionContract(id=option.id.value, label=option.label.value)
                for option in view.question.options
            ),
        )
        if view.question is not None
        else None
    )
    progress_contract = InterviewProgressContract(
        pending=tuple(item.value for item in progress.pending),
        required_pending=tuple(item.value for item in progress.required_pending),
        blocked=tuple(
            InterviewBlockedQuestionContract(
                question_id=item.question_id.value,
                unresolved_dependencies=tuple(
                    dependency.value for dependency in item.unresolved_dependencies
                ),
                required=item.required,
            )
            for item in progress.blocked
        ),
        not_applicable=tuple(item.value for item in progress.not_applicable),
        answered=tuple(item.value for item in progress.answered),
        skipped=tuple(item.value for item in progress.skipped),
        deferred=tuple(item.value for item in progress.deferred),
        required_skipped=tuple(item.value for item in progress.required_skipped),
        required_deferred=tuple(item.value for item in progress.required_deferred),
        complete=progress.is_complete,
        next_question=(progress.next_question.value if progress.next_question else None),
    )
    interaction = InterviewInteractionContract(
        session_id=view.session_id.value,
        questionnaire_id=view.questionnaire_id,
        operation=view.operation,
        changed=view.changed,
        question=question,
        progress=progress_contract,
    )
    return interaction.model_dump(mode="json")


def _render_human(console: Console, data: dict[str, object]) -> None:
    console.print(f"[bold]Interview session:[/bold] {data['session_id']}")
    console.print(f"Operation: {data['operation']}")
    question = data.get("question")
    if isinstance(question, dict):
        console.print(f"[bold cyan]{question['id']}[/bold cyan] — {question['prompt']}")
        console.print(f"Type: {question['type']} | Required: {question['required']}")
        options = question.get("options")
        if isinstance(options, list) and options:
            table = Table("ID", "Label")
            for option in options:
                if isinstance(option, dict):
                    table.add_row(str(option["id"]), str(option["label"]))
            console.print(table)
    else:
        console.print("[green]No actionable question remains.[/green]")
    progress = data["progress"]
    if isinstance(progress, dict):
        console.print(
            f"Progress: {len(progress['answered'])} answered, "
            f"{len(progress['pending'])} pending, "
            f"{len(progress['deferred'])} deferred, "
            f"{len(progress['skipped'])} skipped."
        )
        console.print(f"Complete: {progress['complete']}")


def _parse_answer(value: str) -> object:
    try:
        return json.loads(value)
    except JSONDecodeError:
        return value
