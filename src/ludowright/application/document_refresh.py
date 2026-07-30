"""Incremental, deterministic refresh of generated project documents."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, cast

from ludowright.application.document_templates import (
    DocumentTemplateEngine,
    RenderedDocument,
)
from ludowright.contracts import (
    DocumentManualSectionContract,
    DocumentRefreshRequestContract,
    DocumentRefreshStateContract,
    DocumentSourceHashContract,
)
from ludowright.domain import CorrelationId, EventDraft, EventType, validate_slug
from ludowright.infrastructure import (
    DEFAULT_DOCUMENT_DIRECTORY,
    DEFAULT_EVENT_LOG_PATH,
    DocumentRefreshRepository,
    DocumentRefreshSnapshot,
    EventLog,
    ProjectFilesystem,
    RepositoryPath,
)

_DOCUMENT_OUTPUT_LIMIT = 8 * 1024 * 1024
_DOCUMENT_REFRESH_LOCK = "document-refresh"
_GENERATED_START = "<!-- ludowright:generated:start -->"
_GENERATED_END = "<!-- ludowright:generated:end -->"
_MANUAL_BLOCK_PATTERN = re.compile(
    r'^<!-- ludowright:manual:start id="([a-z0-9]+(?:-[a-z0-9]+)*)" '
    r'approved="(true|false)" -->\n?(.*?)'
    r"^<!-- ludowright:manual:end -->\n?",
    flags=re.MULTILINE | re.DOTALL,
)
_MANUAL_TOKEN_PATTERN = re.compile(r"<!-- ludowright:manual:")

type RefreshStatus = Literal["new", "current", "stale"]


class DocumentRefreshError(RuntimeError):
    """Raised when a document cannot be safely planned or refreshed."""


class DocumentRefreshRollbackError(DocumentRefreshError):
    """Raised when a failed refresh cannot restore its previous files."""


@dataclass(frozen=True, slots=True)
class DocumentRefreshRequest:
    """One render request with explicit source identities."""

    document_id: str
    template_id: str
    context: Mapping[str, object]
    source_hashes: Mapping[str, str] | tuple[DocumentSourceHashContract, ...] = ()
    entrypoint: str | None = None

    def __post_init__(self) -> None:
        try:
            validate_slug(self.document_id)
            validate_slug(self.template_id)
        except ValueError as error:
            raise DocumentRefreshError(str(error)) from error
        if not isinstance(self.context, Mapping):
            raise DocumentRefreshError("document refresh context must be a mapping")
        if isinstance(self.source_hashes, Mapping):
            try:
                sources = tuple(
                    DocumentSourceHashContract(source_id=source_id, digest=digest)
                    for source_id, digest in sorted(self.source_hashes.items())
                )
            except (TypeError, ValueError) as error:
                raise DocumentRefreshError("document source hashes are invalid") from error
        else:
            sources = tuple(self.source_hashes)
        try:
            contract = DocumentRefreshRequestContract(
                document_id=self.document_id,
                template_id=self.template_id,
                entrypoint=self.entrypoint,
                context=dict(self.context),
                source_hashes=sources,
            )
        except ValueError as error:
            raise DocumentRefreshError("document refresh request is invalid") from error
        object.__setattr__(self, "context", contract.context)
        object.__setattr__(self, "source_hashes", contract.source_hashes)

    @classmethod
    def from_contract(cls, value: DocumentRefreshRequestContract) -> DocumentRefreshRequest:
        """Create an application request from the published input contract."""
        return cls(
            document_id=value.document_id,
            template_id=value.template_id,
            entrypoint=value.entrypoint,
            context=value.context,
            source_hashes=value.source_hashes,
        )

    @property
    def source_contracts(self) -> tuple[DocumentSourceHashContract, ...]:
        """Return normalized source hashes for application and persistence code."""
        return cast(tuple[DocumentSourceHashContract, ...], self.source_hashes)


@dataclass(frozen=True, slots=True)
class DocumentRefreshPlan:
    """Deterministic plan for one document, including affected sources."""

    document_id: str
    status: RefreshStatus
    changed_sources: tuple[str, ...]
    reasons: tuple[str, ...]
    output_path: str
    state_path: str
    generated_digest: str
    output_digest: str
    manual_sections: tuple[DocumentManualSectionContract, ...]
    _state_digest: str | None = None

    @property
    def requires_refresh(self) -> bool:
        """Return whether this plan would change canonical project files."""
        return self.status != "current"

    def as_data(self) -> dict[str, object]:
        """Return bounded JSON-compatible data for CLI presentation."""
        return {
            "document_id": self.document_id,
            "status": self.status,
            "changed_sources": list(self.changed_sources),
            "reasons": list(self.reasons),
            "output_path": self.output_path,
            "state_path": self.state_path,
            "generated_digest": self.generated_digest,
            "output_digest": self.output_digest,
            "manual_sections": [
                section.model_dump(mode="json") for section in self.manual_sections
            ],
        }


@dataclass(frozen=True, slots=True)
class DocumentRefreshResult:
    """Result shared by application callers and CLI presentation."""

    plans: tuple[DocumentRefreshPlan, ...]
    dry_run: bool
    refreshed_documents: tuple[str, ...]

    @property
    def affected_documents(self) -> tuple[str, ...]:
        """Return document IDs that are new or stale in deterministic order."""
        return tuple(plan.document_id for plan in self.plans if plan.requires_refresh)

    def as_data(self) -> dict[str, object]:
        """Return the published command data shape."""
        return {
            "schema_version": 1,
            "kind": "document-refresh-report",
            "dry_run": self.dry_run,
            "affected_documents": list(self.affected_documents),
            "refreshed_documents": list(self.refreshed_documents),
            "plans": [plan.as_data() for plan in self.plans],
        }


@dataclass(frozen=True, slots=True)
class _ManualSection:
    value: DocumentManualSectionContract
    block: str


class DocumentRefreshService:
    """Plan and persist deterministic document refreshes behind one lock."""

    def __init__(self, filesystem: ProjectFilesystem) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("document refresh requires ProjectFilesystem")
        self._filesystem = filesystem
        self._templates = DocumentTemplateEngine(filesystem)

    def plan(
        self,
        requests: Iterable[DocumentRefreshRequest],
    ) -> tuple[DocumentRefreshPlan, ...]:
        """Render and compare requests without changing project files."""
        normalized = _normalize_requests(requests)
        return tuple(self._plan_one(request) for request in normalized)

    def refresh(
        self,
        requests: Iterable[DocumentRefreshRequest],
        *,
        dry_run: bool = False,
    ) -> DocumentRefreshResult:
        """Refresh affected documents atomically, or only return their plan."""
        normalized = _normalize_requests(requests)
        if dry_run:
            return DocumentRefreshResult(
                plans=self.plan(normalized),
                dry_run=True,
                refreshed_documents=(),
            )

        with self._filesystem.lock(_DOCUMENT_REFRESH_LOCK, timeout=5.0):
            plans = tuple(self._plan_one(request) for request in normalized)
            affected = tuple(plan for plan in plans if plan.requires_refresh)
            if not affected:
                return DocumentRefreshResult(
                    plans=plans,
                    dry_run=False,
                    refreshed_documents=(),
                )
            self._persist(affected, normalized)
            return DocumentRefreshResult(
                plans=plans,
                dry_run=False,
                refreshed_documents=tuple(plan.document_id for plan in affected),
            )

    def _plan_one(self, request: DocumentRefreshRequest) -> DocumentRefreshPlan:
        rendered = self._templates.render(
            request.template_id,
            request.context,
            entrypoint=request.entrypoint,
        )
        output_path = DEFAULT_DOCUMENT_DIRECTORY.child(f"{request.document_id}.md")
        state_repository = DocumentRefreshRepository(self._filesystem, request.document_id)
        state_snapshot = state_repository.load_optional()
        existing = _read_optional_text(self._filesystem, output_path)
        manual_sections = _extract_manual_sections(existing or "")
        generated = _assemble_generated(rendered)
        if _MANUAL_TOKEN_PATTERN.search(rendered.content):
            raise DocumentRefreshError(
                "generated documents cannot contain reserved manual-section markers"
            )
        output = _append_manual_sections(generated, manual_sections)
        generated_digest = rendered.digest
        output_digest = _digest_text(output)
        current_sources = request.source_contracts
        changed_sources, reasons = _compare_state(
            state_snapshot,
            document_id=request.document_id,
            current_sources=current_sources,
            rendered=rendered,
            output=existing,
            manual_sections=manual_sections,
        )
        status: RefreshStatus = "current"
        if state_snapshot is None:
            status = "new"
        elif reasons:
            status = "stale"
        return DocumentRefreshPlan(
            document_id=request.document_id,
            status=status,
            changed_sources=changed_sources,
            reasons=reasons if reasons else ("up-to-date",),
            output_path=output_path.value,
            state_path=state_repository.path.value,
            generated_digest=generated_digest,
            output_digest=output_digest,
            manual_sections=tuple(section.value for section in manual_sections),
            _state_digest=state_snapshot.digest if state_snapshot is not None else None,
        )

    def _persist(
        self,
        plans: tuple[DocumentRefreshPlan, ...],
        requests: tuple[DocumentRefreshRequest, ...],
    ) -> None:
        request_by_id = {request.document_id: request for request in requests}
        prior_files: dict[RepositoryPath, bytes | None] = {}
        for plan in plans:
            output_path = RepositoryPath(plan.output_path)
            state_path = RepositoryPath(plan.state_path)
            prior_files[output_path] = _read_optional_bytes(self._filesystem, output_path)
            prior_files[state_path] = _read_optional_bytes(self._filesystem, state_path)
        prior_event_log = _read_optional_bytes(self._filesystem, DEFAULT_EVENT_LOG_PATH)

        try:
            for plan in plans:
                request = request_by_id[plan.document_id]
                rendered = self._templates.render(
                    request.template_id,
                    request.context,
                    entrypoint=request.entrypoint,
                )
                existing = _read_optional_text(
                    self._filesystem,
                    RepositoryPath(plan.output_path),
                )
                manual_sections = _extract_manual_sections(existing or "")
                output = _append_manual_sections(_assemble_generated(rendered), manual_sections)
                self._filesystem.write_text(RepositoryPath(plan.output_path), output)
                state = DocumentRefreshStateContract(
                    document_id=plan.document_id,
                    template_id=rendered.template_id,
                    template_version=rendered.template_version,
                    entrypoint=rendered.entrypoint,
                    source_hashes=request.source_contracts,
                    generated_digest=rendered.digest,
                    output_digest=_digest_text(output),
                    status="current",
                    manual_sections=tuple(section.value for section in manual_sections),
                )
                repository = DocumentRefreshRepository(self._filesystem, plan.document_id)
                if plan._state_digest is None:
                    repository.create(state)
                else:
                    repository.save(state, expected_digest=plan._state_digest)

            EventLog(self._filesystem).append(
                EventDraft(
                    event_type=EventType("document.refreshed"),
                    correlation_id=CorrelationId("document-refresh"),
                    payload={
                        "documents": tuple(
                            {
                                "document_id": plan.document_id,
                                "generated_digest": plan.generated_digest,
                                "output_digest": plan.output_digest,
                                "changed_sources": tuple(plan.changed_sources),
                            }
                            for plan in plans
                        )
                    },
                ),
                timeout=5.0,
            )
        except BaseException as error:
            try:
                for path, payload in prior_files.items():
                    if payload is None:
                        self._filesystem.remove_file(path)
                    else:
                        self._filesystem.write_bytes(path, payload)
                if prior_event_log is None:
                    self._filesystem.remove_file(DEFAULT_EVENT_LOG_PATH)
                else:
                    self._filesystem.write_bytes(DEFAULT_EVENT_LOG_PATH, prior_event_log)
            except BaseException as rollback_error:
                raise DocumentRefreshRollbackError(
                    f"document refresh rollback failed after persistence error: {rollback_error}"
                ) from error
            raise


def _normalize_requests(
    requests: Iterable[DocumentRefreshRequest],
) -> tuple[DocumentRefreshRequest, ...]:
    normalized = tuple(requests)
    if any(not isinstance(request, DocumentRefreshRequest) for request in normalized):
        raise TypeError("document refresh requires DocumentRefreshRequest values")
    ids = tuple(request.document_id for request in normalized)
    if len(ids) != len(set(ids)):
        raise DocumentRefreshError("document refresh request IDs must be unique")
    return tuple(sorted(normalized, key=lambda request: request.document_id))


def _compare_state(
    state_snapshot: DocumentRefreshSnapshot | None,
    *,
    document_id: str,
    current_sources: tuple[DocumentSourceHashContract, ...],
    rendered: RenderedDocument,
    output: str | None,
    manual_sections: tuple[_ManualSection, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if state_snapshot is None:
        return tuple(source.source_id for source in current_sources), ("missing-state",)
    state = state_snapshot.value
    reasons: list[str] = []
    if state.document_id != document_id:
        reasons.append("state-document-mismatch")
    previous = {source.source_id: source.digest for source in state.source_hashes}
    current = {source.source_id: source.digest for source in current_sources}
    changed_sources = tuple(
        sorted(
            source_id
            for source_id in set(previous) | set(current)
            if previous.get(source_id) != current.get(source_id)
        )
    )
    if changed_sources:
        reasons.append("source-changed")
    if (
        state.template_id != rendered.template_id
        or state.template_version != rendered.template_version
    ):
        reasons.append("template-changed")
    if state.entrypoint != rendered.entrypoint:
        reasons.append("entrypoint-changed")
    if state.generated_digest != rendered.digest:
        reasons.append("generated-content-changed")
    if output is None:
        reasons.append("output-missing")
    elif state.output_digest != _digest_text(output):
        reasons.append("output-changed")
    state_manual = {section.id: section.digest for section in state.manual_sections}
    current_manual = {section.value.id: section.value.digest for section in manual_sections}
    if state_manual != current_manual:
        reasons.append("manual-section-changed")
    if state.status != "current":
        reasons.append("state-marked-stale")
    return changed_sources, tuple(dict.fromkeys(reasons))


def _extract_manual_sections(text: str) -> tuple[_ManualSection, ...]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    sections: list[_ManualSection] = []
    consumed: list[tuple[int, int]] = []
    for match in _MANUAL_BLOCK_PATTERN.finditer(normalized):
        body = match.group(3)
        if _MANUAL_TOKEN_PATTERN.search(body):
            raise DocumentRefreshError("manual sections cannot be nested")
        block = match.group(0).rstrip("\n") + "\n"
        sections.append(
            _ManualSection(
                value=DocumentManualSectionContract(
                    id=match.group(1),
                    approved=match.group(2) == "true",
                    digest=_digest_text(block),
                ),
                block=block,
            )
        )
        consumed.append(match.span())
    remaining = normalized
    for start, end in reversed(consumed):
        remaining = remaining[:start] + remaining[end:]
    if _MANUAL_TOKEN_PATTERN.search(remaining):
        raise DocumentRefreshError("manual section markers are incomplete or malformed")
    identifiers = tuple(section.value.id for section in sections)
    if len(identifiers) != len(set(identifiers)):
        raise DocumentRefreshError("manual section IDs must be unique")
    return tuple(sections)


def _assemble_generated(rendered: RenderedDocument) -> str:
    return f"{_GENERATED_START}\n{rendered.content.rstrip(chr(10))}\n{_GENERATED_END}\n"


def _append_manual_sections(generated: str, sections: tuple[_ManualSection, ...]) -> str:
    if not sections:
        return generated
    return generated + "\n" + "\n".join(section.block.rstrip("\n") for section in sections) + "\n"


def _read_optional_text(filesystem: ProjectFilesystem, path: RepositoryPath) -> str | None:
    payload = _read_optional_bytes(filesystem, path)
    if payload is None:
        return None
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DocumentRefreshError(f"document output is not valid UTF-8: {path}") from error


def _read_optional_bytes(filesystem: ProjectFilesystem, path: RepositoryPath) -> bytes | None:
    try:
        return filesystem.read_bytes(path, max_bytes=_DOCUMENT_OUTPUT_LIMIT)
    except FileNotFoundError:
        return None


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
