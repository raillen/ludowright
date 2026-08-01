"""Deterministic discovery and explicit confirmation of assets in Markdown."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from pydantic import ValidationError

from ludowright.application.asset_registry import (
    DEFAULT_ASSET_REGISTRY_PATH,
    AssetRegistryService,
)
from ludowright.application.asset_taxonomy import (
    AssetTaxonomy,
    AssetTaxonomyError,
    load_asset_taxonomy,
)
from ludowright.contracts import (
    AssetContract,
    AssetDiscoveryCandidateContract,
    AssetDiscoveryIssueContract,
    AssetDiscoveryReportContract,
)
from ludowright.contracts.asset_discovery import (
    AssetDiscoveryIssueCode,
    AssetDiscoveryState,
)
from ludowright.domain import (
    AssetFamily,
    AssetPriority,
    DomainValidationError,
    FrozenJsonValue,
    slugify,
    validate_slug,
)
from ludowright.infrastructure import (
    DEFAULT_DOCUMENT_DIRECTORY,
    ProjectFilesystem,
    RepositoryPath,
)

_DOCUMENT_READ_LIMIT = 2_000_000
_MAX_CONFIRMATION_CANDIDATES = 256
_MARKER_START = re.compile(r"^\s*<!--\s*ludowright:asset-candidate(?:\s|-->)")
_MARKER_LINE = re.compile(
    r"^\s*<!--\s*ludowright:asset-candidate(?P<attributes>.*?)\s*-->"
    r"\s*:?[ \t]*(?P<name>\S.*?)\s*$"
)
_ATTRIBUTE = re.compile(r'(?P<key>[a-z][a-z0-9_-]*)="(?P<value>[^"\r\n]*)"')
_FENCE = re.compile(r"^\s*(?P<delimiter>`{3,}|~{3,})")
_ALLOWED_ATTRIBUTES = frozenset({"id", "family", "subtype", "priority"})
_REQUIRED_ATTRIBUTES = frozenset({"family"})


class AssetDiscoveryError(RuntimeError):
    """Base failure for safe asset discovery and confirmation."""


class AssetDiscoveryConfirmationError(AssetDiscoveryError):
    """Raised when explicit confirmation cannot be safely applied."""

    def __init__(self, message: str, report: AssetDiscoveryReportContract) -> None:
        super().__init__(message)
        self.report = report


@dataclass(frozen=True, slots=True)
class AssetDiscoveryResult:
    """Stable result shared by application callers and CLI renderers."""

    report: AssetDiscoveryReportContract

    def as_data(self) -> dict[str, object]:
        """Return the published JSON-compatible report."""
        return self.report.model_dump(mode="json")


class AssetDiscoveryService:
    """Extract explicit candidates and create only confirmed assets."""

    def __init__(
        self,
        filesystem: ProjectFilesystem,
        *,
        taxonomy: AssetTaxonomy | None = None,
    ) -> None:
        if not isinstance(filesystem, ProjectFilesystem):
            raise TypeError("asset discovery requires ProjectFilesystem")
        self._filesystem = filesystem
        self._taxonomy = taxonomy or load_asset_taxonomy()
        self._registry = AssetRegistryService(filesystem, taxonomy=self._taxonomy)

    def discover(
        self,
        *,
        source_paths: Iterable[RepositoryPath] = (),
        confirm_ids: Iterable[str] = (),
        dry_run: bool = False,
    ) -> AssetDiscoveryResult:
        """Scan Markdown and optionally confirm selected pending candidates."""
        paths = self._source_paths(source_paths)
        registry = self._registry.list_assets()
        extracted, candidate_assets, issues = self._extract(paths)
        existing_ids = {asset.id for asset in registry.assets}
        candidates, issues = self._annotate(
            extracted,
            existing_ids=existing_ids,
            issues=issues,
        )
        report = self._report(
            source_paths=paths,
            candidates=candidates,
            issues=issues,
            dry_run=dry_run,
            registry_version=registry.registry_version,
        )
        selected_ids = self._confirmation_ids(confirm_ids)
        if not selected_ids:
            return AssetDiscoveryResult(report=report)
        if len(selected_ids) > _MAX_CONFIRMATION_CANDIDATES:
            raise AssetDiscoveryConfirmationError(
                f"a confirmation operation cannot contain more than "
                f"{_MAX_CONFIRMATION_CANDIDATES} candidates",
                report,
            )

        selected, report = self._select_for_confirmation(report, candidate_assets, selected_ids)
        event_candidates: tuple[Mapping[str, FrozenJsonValue], ...] = tuple(
            {
                "candidate_id": candidate.candidate_id,
                "source_line": candidate.source_line,
                "source_path": candidate.source_path,
            }
            for candidate in selected
        )
        registry_result = self._registry.create_many(
            tuple(candidate_assets[candidate.candidate_id] for candidate in selected),
            dry_run=dry_run,
            event_type="asset.discovered",
            event_payload={"discovery_candidates": event_candidates},
            operation="discover",
        )
        confirmed_ids = tuple(sorted(asset.id for asset in registry_result.assets))
        confirmed_candidates = tuple(
            candidate.model_copy(update={"state": "confirmed"})
            if candidate.candidate_id in selected_ids
            else candidate
            for candidate in report.candidates
        )
        state = "planned" if dry_run else "confirmed"
        return AssetDiscoveryResult(
            report=report.model_copy(
                update={
                    "candidates": confirmed_candidates,
                    "confirmed_asset_ids": confirmed_ids,
                    "registry_version": registry_result.registry_version,
                    "state": state,
                    "valid": not report.issues,
                }
            )
        )

    @staticmethod
    def _confirmation_ids(confirm_ids: Iterable[str]) -> tuple[str, ...]:
        requested = tuple(confirm_ids)
        if any(not isinstance(candidate_id, str) for candidate_id in requested):
            raise AssetDiscoveryError("confirmation IDs must be strings")
        try:
            for candidate_id in requested:
                validate_slug(candidate_id)
        except ValueError as error:
            raise AssetDiscoveryError(str(error)) from error
        return tuple(sorted(set(requested)))

    def _source_paths(self, source_paths: Iterable[RepositoryPath]) -> tuple[RepositoryPath, ...]:
        requested = tuple(source_paths)
        if any(not isinstance(path, RepositoryPath) for path in requested):
            raise TypeError("asset discovery source paths require RepositoryPath values")
        if requested:
            paths = tuple(sorted(requested, key=lambda path: path.value))
            if len(paths) != len({path.value for path in paths}):
                raise AssetDiscoveryError("asset discovery source paths must be unique")
        else:
            paths = self._filesystem.list_files(
                DEFAULT_DOCUMENT_DIRECTORY,
                suffix=".md",
                max_files=10_000,
            )
        prefix = DEFAULT_DOCUMENT_DIRECTORY.parts
        for path in paths:
            if path.parts[: len(prefix)] != prefix or not path.name.endswith(".md"):
                raise AssetDiscoveryError(
                    "asset discovery sources must be Markdown files under "
                    f"{DEFAULT_DOCUMENT_DIRECTORY}"
                )
        return paths

    def _extract(
        self,
        paths: tuple[RepositoryPath, ...],
    ) -> tuple[
        tuple[AssetDiscoveryCandidateContract, ...],
        dict[str, AssetContract],
        tuple[AssetDiscoveryIssueContract, ...],
    ]:
        candidates: list[AssetDiscoveryCandidateContract] = []
        candidate_assets: dict[str, AssetContract] = {}
        issues: list[AssetDiscoveryIssueContract] = []
        for path in paths:
            try:
                text = self._filesystem.read_text(path, max_bytes=_DOCUMENT_READ_LIMIT)
            except UnicodeDecodeError as error:
                raise AssetDiscoveryError(
                    f"asset discovery document is not valid UTF-8: {path}"
                ) from error
            fence: tuple[str, int] | None = None
            for line_number, line in enumerate(text.splitlines(), start=1):
                fence_match = _FENCE.match(line)
                if fence is not None:
                    if (
                        fence_match is not None
                        and fence_match.group("delimiter")[0] == fence[0]
                        and len(fence_match.group("delimiter")) >= fence[1]
                    ):
                        fence = None
                    continue
                if fence_match is not None:
                    delimiter = fence_match.group("delimiter")
                    fence = (delimiter[0], len(delimiter))
                    continue
                if not _MARKER_START.match(line):
                    continue
                try:
                    candidate, asset = self._parse_marker(path, line_number, line)
                except (
                    AssetDiscoveryError,
                    AssetTaxonomyError,
                    DomainValidationError,
                    ValidationError,
                ) as error:
                    issues.append(
                        _issue(
                            code="invalid-declaration",
                            subject=f"{path.value}#L{line_number}",
                            message=str(error),
                            source_paths=(path.value,),
                        )
                    )
                    continue
                if candidate.candidate_id in candidate_assets:
                    issues.append(
                        _issue(
                            code="duplicate-candidate",
                            subject=candidate.candidate_id,
                            message="two declarations produced the same candidate ID",
                            candidate_ids=(candidate.candidate_id,),
                            source_paths=(candidate.source_path,),
                        )
                    )
                    continue
                candidates.append(candidate)
                candidate_assets[candidate.candidate_id] = asset
        return tuple(candidates), candidate_assets, tuple(issues)

    def _parse_marker(
        self,
        path: RepositoryPath,
        line_number: int,
        line: str,
    ) -> tuple[AssetDiscoveryCandidateContract, AssetContract]:
        match = _MARKER_LINE.fullmatch(line)
        if match is None:
            raise AssetDiscoveryError(
                "asset candidate declaration must use quoted attributes and a display name"
            )
        attributes = _parse_attributes(match.group("attributes"))
        missing = _REQUIRED_ATTRIBUTES.difference(attributes)
        if missing:
            raise AssetDiscoveryError(
                "asset candidate declaration is missing: " + ", ".join(sorted(missing))
            )
        name = match.group("name").strip()
        if len(line.strip()) > 4_000:
            raise AssetDiscoveryError("asset candidate evidence exceeds 4,000 characters")
        try:
            family = AssetFamily(attributes["family"])
            priority = AssetPriority(attributes.get("priority", AssetPriority.NORMAL.value))
        except ValueError as error:
            raise AssetDiscoveryError(str(error)) from error
        subtype = attributes.get("subtype")
        self._taxonomy.validate_classification(family, subtype)
        asset_id = attributes.get("id")
        if asset_id is None:
            slug = slugify(name)
            asset_id = f"{self._taxonomy.naming_rule(family).prefix}-{slug}"
        self._taxonomy.validate_asset_id(family, asset_id)
        asset = AssetContract(
            id=asset_id,
            name=name,
            family=family,
            subtype=subtype,
            priority=priority,
        )
        asset.to_domain()
        candidate_id = _candidate_id(path, line_number, line)
        candidate = AssetDiscoveryCandidateContract(
            candidate_id=candidate_id,
            asset_id=asset.id,
            name=asset.name,
            family=asset.family,
            subtype=asset.subtype,
            priority=asset.priority,
            source_path=path.value,
            source_line=line_number,
            evidence=line.strip(),
        )
        return candidate, asset

    def _annotate(
        self,
        candidates: tuple[AssetDiscoveryCandidateContract, ...],
        *,
        existing_ids: set[str],
        issues: tuple[AssetDiscoveryIssueContract, ...],
    ) -> tuple[
        tuple[AssetDiscoveryCandidateContract, ...], tuple[AssetDiscoveryIssueContract, ...]
    ]:
        grouped: defaultdict[str, list[AssetDiscoveryCandidateContract]] = defaultdict(list)
        for candidate in candidates:
            grouped[candidate.asset_id].append(candidate)
        annotated: list[AssetDiscoveryCandidateContract] = []
        additional: list[AssetDiscoveryIssueContract] = []
        for asset_id, grouped_candidates in sorted(grouped.items()):
            candidate_ids = tuple(sorted(item.candidate_id for item in grouped_candidates))
            source_paths = tuple(sorted(item.source_path for item in grouped_candidates))
            if len(grouped_candidates) > 1:
                additional.append(
                    _issue(
                        code="duplicate-asset-id",
                        subject=asset_id,
                        message="multiple document declarations suggest the same asset ID",
                        candidate_ids=candidate_ids,
                        source_paths=source_paths,
                    )
                )
            elif asset_id in existing_ids:
                additional.append(
                    _issue(
                        code="existing-asset-id",
                        subject=asset_id,
                        message="the suggested asset ID already exists in the registry",
                        candidate_ids=candidate_ids,
                        source_paths=source_paths,
                    )
                )
            for candidate in grouped_candidates:
                state = "pending"
                if len(grouped_candidates) > 1:
                    state = "ambiguous"
                elif asset_id in existing_ids:
                    state = "rejected"
                annotated.append(candidate.model_copy(update={"state": state}))
        return (
            tuple(sorted(annotated, key=lambda candidate: candidate.candidate_id)),
            tuple(sorted((*issues, *additional), key=_issue_sort_key)),
        )

    def _select_for_confirmation(
        self,
        report: AssetDiscoveryReportContract,
        candidate_assets: Mapping[str, AssetContract],
        selected_ids: tuple[str, ...],
    ) -> tuple[tuple[AssetDiscoveryCandidateContract, ...], AssetDiscoveryReportContract]:
        by_id = {candidate.candidate_id: candidate for candidate in report.candidates}
        missing = tuple(candidate_id for candidate_id in selected_ids if candidate_id not in by_id)
        blocked = tuple(
            candidate_id
            for candidate_id in selected_ids
            if candidate_id in by_id and by_id[candidate_id].state != "pending"
        )
        if missing or blocked:
            issues = list(report.issues)
            if missing:
                issues.append(
                    _issue(
                        code="candidate-not-found",
                        subject="confirmation",
                        message="requested candidate IDs were not found",
                        candidate_ids=missing,
                    )
                )
            if blocked:
                issues.append(
                    _issue(
                        code="confirmation-blocked",
                        subject="confirmation",
                        message="ambiguous or already-used candidates cannot be confirmed",
                        candidate_ids=blocked,
                    )
                )
            failed = report.model_copy(
                update={
                    "issues": tuple(sorted(issues, key=_issue_sort_key)),
                    "state": "ambiguous",
                    "valid": False,
                }
            )
            raise AssetDiscoveryConfirmationError(
                "asset confirmation requires existing, unambiguous pending candidates",
                failed,
            )
        selected = tuple(by_id[candidate_id] for candidate_id in selected_ids)
        if any(candidate_id not in candidate_assets for candidate_id in selected_ids):
            raise AssetDiscoveryConfirmationError(
                "asset confirmation candidates have no validated asset payload",
                report,
            )
        return selected, report

    @staticmethod
    def _report(
        *,
        source_paths: tuple[RepositoryPath, ...],
        candidates: tuple[AssetDiscoveryCandidateContract, ...],
        issues: tuple[AssetDiscoveryIssueContract, ...],
        dry_run: bool,
        registry_version: int,
    ) -> AssetDiscoveryReportContract:
        state: AssetDiscoveryState = "empty"
        if candidates or issues:
            state = (
                "invalid"
                if any(issue.code == "invalid-declaration" for issue in issues)
                else "pending"
            )
        if any(issue.code in {"duplicate-asset-id", "existing-asset-id"} for issue in issues):
            state = "ambiguous"
        return AssetDiscoveryReportContract(
            state=state,
            dry_run=dry_run,
            source_paths=tuple(path.value for path in source_paths),
            candidates=tuple(sorted(candidates, key=lambda candidate: candidate.candidate_id)),
            issues=tuple(sorted(issues, key=_issue_sort_key)),
            registry_path=DEFAULT_ASSET_REGISTRY_PATH.value,
            registry_version=registry_version,
            valid=not issues,
        )


def _parse_attributes(value: str) -> dict[str, str]:
    attributes: dict[str, str] = {}
    cursor = 0
    while cursor < len(value):
        while cursor < len(value) and value[cursor].isspace():
            cursor += 1
        if cursor == len(value):
            break
        match = _ATTRIBUTE.match(value, cursor)
        if match is None:
            raise AssetDiscoveryError("asset candidate attributes are malformed")
        key = match.group("key")
        if key not in _ALLOWED_ATTRIBUTES:
            raise AssetDiscoveryError(f"asset candidate attribute is not supported: {key}")
        if key in attributes:
            raise AssetDiscoveryError(f"asset candidate attribute is repeated: {key}")
        attributes[key] = match.group("value")
        cursor = match.end()
    return attributes


def _candidate_id(path: RepositoryPath, line_number: int, line: str) -> str:
    source = f"{path.value}\n{line_number}\n{line.strip()}".encode()
    return f"candidate-{hashlib.sha256(source).hexdigest()}"


def _issue(
    *,
    code: AssetDiscoveryIssueCode,
    subject: str,
    message: str,
    candidate_ids: tuple[str, ...] = (),
    source_paths: tuple[str, ...] = (),
) -> AssetDiscoveryIssueContract:
    return AssetDiscoveryIssueContract(
        code=code,
        subject=subject,
        message=message[:4_000],
        candidate_ids=tuple(sorted(candidate_ids)),
        source_paths=tuple(sorted(source_paths)),
    )


def _issue_sort_key(issue: AssetDiscoveryIssueContract) -> tuple[str, str, tuple[str, ...]]:
    return issue.code, issue.subject, issue.candidate_ids
