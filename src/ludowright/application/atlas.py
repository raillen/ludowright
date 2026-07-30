"""Deterministic documentation indexing and integrity analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final
from urllib.parse import unquote, urlsplit

from pydantic import ValidationError

from ludowright.contracts import (
    AtlasBrokenLinkContract,
    AtlasDocumentMetadataContract,
    AtlasLinkContract,
    AtlasMetadataContract,
    AtlasReportContract,
)
from ludowright.infrastructure import (
    DocumentationFilesystem,
    DocumentationFilesystemError,
    JsonDocumentRepository,
    ProjectFilesystem,
    ProjectFilesystemError,
    RepositoryPath,
    StructuredDocumentError,
)

_MARKDOWN_LINK_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<!\!)\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))"
)
_HEADING_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_MARKDOWN_FORMATTING_PATTERN: Final[re.Pattern[str]] = re.compile(r"[`*_~]")


class AtlasGenerationError(RuntimeError):
    """Raised when atlas metadata or source documents cannot be analyzed."""


@dataclass(frozen=True, slots=True)
class AtlasGeneration:
    """A report and its deterministic Markdown index projection."""

    report: AtlasReportContract
    markdown: str

    @property
    def valid(self) -> bool:
        """Return whether all links and metadata references resolved."""
        return not self.report.broken_links and not self.report.orphan_documents


class AtlasGenerator:
    """Build an index from canonical metadata and a safe Markdown tree."""

    def __init__(
        self,
        root: Path | str,
        *,
        docs_directory: str = "docs",
        metadata_path: str = "docs/atlas.json",
    ) -> None:
        try:
            self._documentation = DocumentationFilesystem(root, docs_directory=docs_directory)
            self._metadata_path = RepositoryPath.parse(metadata_path)
            self._metadata_repository = JsonDocumentRepository(
                ProjectFilesystem(self._documentation.root),
                self._metadata_path,
                AtlasMetadataContract,
            )
        except (DocumentationFilesystemError, ValueError, TypeError) as error:
            raise AtlasGenerationError("atlas inputs are not safe or usable") from error

    def generate(self) -> AtlasGeneration:
        """Load metadata, scan Markdown, and return a deterministic report."""
        try:
            metadata_snapshot = self._metadata_repository.load()
            metadata = metadata_snapshot.value
            discovered = self._documentation.list_markdown()
        except (
            DocumentationFilesystemError,
            FileNotFoundError,
            OSError,
            ProjectFilesystemError,
            StructuredDocumentError,
        ) as error:
            raise AtlasGenerationError(f"atlas inputs could not be read: {error}") from error
        except ValidationError as error:
            raise AtlasGenerationError("atlas metadata is invalid") from error

        discovered_set = set(discovered)
        metadata_documents = tuple(sorted(metadata.documents, key=lambda document: document.path))
        metadata_paths = {document.path for document in metadata_documents}
        broken_links = self._metadata_issues(metadata_documents, discovered_set)
        links: list[AtlasLinkContract] = []

        for source in discovered:
            content = self._read(source)
            for raw_target in _extract_link_targets(content):
                link, issue = self._inspect_link(source, raw_target)
                if link is not None:
                    links.append(link)
                if issue is not None:
                    broken_links.append(issue)

        report = AtlasReportContract(
            version=metadata.version,
            metadata_digest=metadata_snapshot.digest,
            documents=metadata_documents,
            links=tuple(sorted(links, key=_link_sort_key)),
            broken_links=tuple(sorted(broken_links, key=_broken_link_sort_key)),
            orphan_documents=tuple(sorted(discovered_set - metadata_paths)),
        )
        return AtlasGeneration(report=report, markdown=render_atlas_markdown(report))

    def _metadata_issues(
        self,
        documents: tuple[AtlasDocumentMetadataContract, ...],
        discovered: set[str],
    ) -> list[AtlasBrokenLinkContract]:
        issues: list[AtlasBrokenLinkContract] = []
        for document in documents:
            if document.path not in discovered:
                issues.append(
                    AtlasBrokenLinkContract(
                        source=document.path,
                        target=document.path,
                        reason="missing-canonical-source",
                    )
                )
            if (
                document.canonical_source != document.path or document.path in discovered
            ) and not self._exists(document.canonical_source):
                issues.append(
                    AtlasBrokenLinkContract(
                        source=document.path,
                        target=document.canonical_source,
                        reason="missing-canonical-source",
                    )
                )
        return issues

    def _read(self, path: str) -> str:
        try:
            return self._documentation.read_markdown(path)
        except (DocumentationFilesystemError, FileNotFoundError, OSError) as error:
            raise AtlasGenerationError(f"atlas document could not be read: {path}") from error

    def _exists(self, path: str) -> bool:
        try:
            return self._documentation.exists(path)
        except DocumentationFilesystemError:
            return False

    def _inspect_link(
        self,
        source: str,
        raw_target: str,
    ) -> tuple[AtlasLinkContract | None, AtlasBrokenLinkContract | None]:
        parsed = urlsplit(raw_target)
        if parsed.scheme or parsed.netloc:
            return None, None

        raw_path = unquote(parsed.path)
        fragment = unquote(parsed.fragment) or None
        if not raw_path:
            normalized_path = source
        else:
            try:
                normalized_path = _resolve_link_path(source, raw_path)
            except ValueError:
                return (
                    None,
                    AtlasBrokenLinkContract(
                        source=source,
                        target=raw_target,
                        reason="unsafe-path",
                        fragment=fragment,
                    ),
                )

        link = AtlasLinkContract(
            source=source,
            target=normalized_path,
            fragment=fragment,
        )
        if not self._exists(normalized_path):
            return link, AtlasBrokenLinkContract(
                source=source,
                target=normalized_path,
                reason="missing-file",
                fragment=fragment,
            )
        if (
            fragment
            and normalized_path.lower().endswith(".md")
            and not _contains_anchor(self._read(normalized_path), fragment)
        ):
            return link, AtlasBrokenLinkContract(
                source=source,
                target=normalized_path,
                reason="missing-anchor",
                fragment=fragment,
            )
        return link, None


def render_atlas_markdown(report: AtlasReportContract) -> str:
    """Render a deterministic human-readable index from one report."""
    lines = [
        "# Generated Documentation Atlas",
        "",
        "This index is derived from versioned ATLAS metadata.",
        "",
    ]
    grouped: dict[str, list[AtlasDocumentMetadataContract]] = {}
    for document in report.documents:
        grouped.setdefault(document.section, []).append(document)

    for section in sorted(grouped):
        lines.extend((f"## {_section_title(section)}", ""))
        for document in sorted(grouped[section], key=lambda item: item.path):
            title = document.title.replace("\\", "\\\\").replace("]", "\\]")
            lines.append(
                f"- [{title}]({document.path}) — canonical source: `{document.canonical_source}`"
            )
        lines.append("")

    lines.extend(
        (
            "## Integrity",
            "",
            f"- Documents: {len(report.documents)}",
            f"- Links: {len(report.links)}",
            f"- Broken links: {len(report.broken_links)}",
            f"- Orphan documents: {len(report.orphan_documents)}",
            "- Status: "
            f"{'valid' if not report.broken_links and not report.orphan_documents else 'invalid'}",
            "",
        )
    )
    return "\n".join(lines)


def _extract_link_targets(content: str) -> tuple[str, ...]:
    return tuple(
        match.group(1) or match.group(2) for match in _MARKDOWN_LINK_PATTERN.finditer(content)
    )


def _resolve_link_path(source: str, target: str) -> str:
    if "\\" in target or target.startswith("/"):
        raise ValueError("link path is not a safe relative POSIX path")
    segments = list(PurePosixPath(source).parent.parts)
    for segment in target.split("/"):
        if not segment or segment == ".":
            continue
        if segment == "..":
            if not segments:
                raise ValueError("link path escapes the documentation root")
            segments.pop()
            continue
        if not segment.isascii() or any(
            not (character.isalnum() or character in "._-") for character in segment
        ):
            raise ValueError("link path contains an unsafe segment")
        segments.append(segment)
    if not segments:
        raise ValueError("link path cannot resolve to the documentation root")
    return "/".join(segments)


def _contains_anchor(content: str, fragment: str) -> bool:
    wanted = _slugify_heading(fragment)
    seen: dict[str, int] = {}
    for line in content.splitlines():
        match = _HEADING_PATTERN.match(line)
        if match is None:
            continue
        slug = _slugify_heading(match.group(1))
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        actual = slug if count == 0 else f"{slug}-{count}"
        if actual == wanted:
            return True
    return False


def _slugify_heading(value: str) -> str:
    value = _MARKDOWN_FORMATTING_PATTERN.sub("", value).strip().lower()
    value = "".join(
        character if character.isalnum() or character in " -_" else "" for character in value
    )
    return "-".join(value.replace("_", "-").split()).strip("-")


def _section_title(value: str) -> str:
    return value.replace("-", " ").title()


def _link_sort_key(link: AtlasLinkContract) -> tuple[str, str, str]:
    return link.source, link.target, link.fragment or ""


def _broken_link_sort_key(link: AtlasBrokenLinkContract) -> tuple[str, str, str, str]:
    return link.source, link.target, link.reason, link.fragment or ""
