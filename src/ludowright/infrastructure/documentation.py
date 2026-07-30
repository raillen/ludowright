"""Safe read-only access to repository documentation trees."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from pathlib import Path


class DocumentationFilesystemError(RuntimeError):
    """Base error for documentation-tree access."""


class UnsafeDocumentationPathError(DocumentationFilesystemError):
    """Raised when a documentation path is unsafe or leaves the root."""


class DocumentationRootError(DocumentationFilesystemError):
    """Raised when the documentation root cannot be used safely."""


class DocumentationFilesystem:
    """Read a bounded Markdown tree without following project symlinks."""

    def __init__(
        self,
        root: Path | str,
        *,
        docs_directory: str = "docs",
        max_document_bytes: int = 2_000_000,
        max_markdown_files: int = 10_000,
    ) -> None:
        if isinstance(max_document_bytes, bool) or max_document_bytes < 1:
            raise ValueError("documentation byte limit must be a positive integer")
        if isinstance(max_markdown_files, bool) or max_markdown_files < 1:
            raise ValueError("documentation file limit must be a positive integer")
        candidate = Path(root).expanduser()
        if candidate.is_symlink():
            raise UnsafeDocumentationPathError("documentation root cannot be a symlink")
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as error:
            raise DocumentationRootError(
                f"documentation repository does not exist: {candidate}"
            ) from error
        if not resolved.is_dir():
            raise DocumentationRootError(f"documentation repository is not a directory: {resolved}")
        self._root = resolved
        self._docs_root = self._resolve_relative(docs_directory, expect_directory=True)
        self._max_document_bytes = max_document_bytes
        self._max_markdown_files = max_markdown_files

    @property
    def root(self) -> Path:
        """Return the resolved repository root."""
        return self._root

    @property
    def docs_root(self) -> Path:
        """Return the resolved Markdown root."""
        return self._docs_root

    def list_markdown(self) -> tuple[str, ...]:
        """Return all Markdown paths relative to the documentation root."""
        paths = tuple(self._walk_markdown(self._docs_root, ()))
        if len(paths) > self._max_markdown_files:
            raise DocumentationFilesystemError(
                f"documentation tree exceeds the {self._max_markdown_files}-file limit"
            )
        return tuple(sorted(paths))

    def read_markdown(self, path: str) -> str:
        """Read one Markdown file after validating every path component."""
        target = self._resolve_document(path, expect_file=True)
        target_stat = os.lstat(target)
        if target_stat.st_size > self._max_document_bytes:
            raise DocumentationFilesystemError(
                f"documentation file exceeds the {self._max_document_bytes}-byte limit: {path}"
            )
        try:
            payload = target.read_bytes()
            if len(payload) > self._max_document_bytes:
                raise DocumentationFilesystemError(
                    "documentation file grew beyond the "
                    f"{self._max_document_bytes}-byte limit: {path}"
                )
            return payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise DocumentationFilesystemError(
                f"documentation file is not valid UTF-8: {path}"
            ) from error

    def exists(self, path: str) -> bool:
        """Return whether one safe documentation-relative regular file exists."""
        target = self._resolve_document(path, expect_file=False)
        if not os.path.lexists(target):
            return False
        target_stat = os.lstat(target)
        if stat.S_ISLNK(target_stat.st_mode):
            raise UnsafeDocumentationPathError(f"documentation path contains a symlink: {path}")
        return stat.S_ISREG(target_stat.st_mode)

    def _walk_markdown(self, directory: Path, prefix: tuple[str, ...]) -> Iterator[str]:
        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError as error:
            raise DocumentationFilesystemError(
                f"cannot inspect documentation directory: {directory}"
            ) from error
        for child in children:
            child_stat = os.lstat(child)
            if stat.S_ISLNK(child_stat.st_mode):
                raise UnsafeDocumentationPathError(
                    f"documentation tree contains a symlink: {child}"
                )
            relative_parts = (*prefix, child.name)
            if stat.S_ISDIR(child_stat.st_mode):
                yield from self._walk_markdown(child, relative_parts)
            elif stat.S_ISREG(child_stat.st_mode) and child.suffix == ".md":
                yield "/".join(relative_parts)

    def _resolve_document(self, path: str, *, expect_file: bool) -> Path:
        _validate_relative_path(path)
        target = self._docs_root.joinpath(*path.split("/"))
        self._assert_inside_docs(target)
        self._assert_safe_prefix(target)
        if expect_file:
            if not os.path.lexists(target):
                raise FileNotFoundError(target)
            target_stat = os.lstat(target)
            if stat.S_ISLNK(target_stat.st_mode):
                raise UnsafeDocumentationPathError(f"documentation path contains a symlink: {path}")
            if not stat.S_ISREG(target_stat.st_mode):
                raise DocumentationFilesystemError(
                    f"documentation path is not a regular file: {path}"
                )
        return target

    def _resolve_relative(self, path: str, *, expect_directory: bool) -> Path:
        _validate_relative_path(path)
        target = self._root.joinpath(*path.split("/"))
        self._assert_inside_root(target)
        self._assert_safe_prefix(target)
        if not os.path.lexists(target):
            raise DocumentationRootError(f"documentation directory does not exist: {path}")
        target_stat = os.lstat(target)
        if stat.S_ISLNK(target_stat.st_mode):
            raise UnsafeDocumentationPathError(
                f"documentation directory cannot be a symlink: {path}"
            )
        if expect_directory and not stat.S_ISDIR(target_stat.st_mode):
            raise DocumentationRootError(f"documentation path is not a directory: {path}")
        return target

    def _assert_inside_root(self, target: Path) -> None:
        try:
            target.relative_to(self._root)
        except ValueError as error:
            raise UnsafeDocumentationPathError(
                f"documentation path escapes the repository: {target}"
            ) from error

    def _assert_inside_docs(self, target: Path) -> None:
        try:
            target.relative_to(self._docs_root)
        except ValueError as error:
            raise UnsafeDocumentationPathError(
                f"documentation path escapes the docs root: {target}"
            ) from error

    @staticmethod
    def _assert_safe_prefix(target: Path) -> None:
        current = (target.anchor and Path(target.anchor)) or Path()
        for component in target.parts:
            current = current / component
            if os.path.lexists(current) and stat.S_ISLNK(os.lstat(current).st_mode):
                raise UnsafeDocumentationPathError(
                    f"documentation path contains a symlink: {current}"
                )


def _validate_relative_path(value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise UnsafeDocumentationPathError("documentation paths must be non-empty strings")
    if not value.isascii() or "\\" in value or value.startswith("/"):
        raise UnsafeDocumentationPathError("documentation paths must be relative ASCII POSIX paths")
    segments = value.split("/")
    for segment in segments:
        if not segment or segment in {".", ".."}:
            raise UnsafeDocumentationPathError(
                "documentation paths cannot contain traversal segments"
            )
        if any(not (character.isalnum() or character in "._-") for character in segment):
            raise UnsafeDocumentationPathError("documentation paths contain an unsafe segment")
