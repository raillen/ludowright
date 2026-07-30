"""Safe repository-relative project filesystem operations."""

from __future__ import annotations

import json
import math
import os
import socket
import stat
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from types import TracebackType
from typing import Self

_MAX_REPOSITORY_PATH_LENGTH = 1_024
_MAX_SEGMENT_LENGTH = 255
_MAX_LOCK_METADATA_BYTES = 16_384
_ALLOWED_SEGMENT_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789._-")
_RESERVED_WINDOWS_NAMES = {
    "aux",
    "clock$",
    "con",
    "nul",
    "prn",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


class ProjectFilesystemError(RuntimeError):
    """Base class for project filesystem failures."""


class ProjectRootNotFoundError(ProjectFilesystemError):
    """Raised when no LudoWright project marker is found."""


class UnsafeProjectPathError(ProjectFilesystemError):
    """Raised when a path could escape or vary across platforms."""


class ProjectLockTimeoutError(ProjectFilesystemError):
    """Raised when an exclusive project lock cannot be acquired in time."""


class ProjectLockOwnershipError(ProjectFilesystemError):
    """Raised when a lock no longer belongs to the releasing process."""


@dataclass(frozen=True, slots=True)
class RepositoryPath:
    """A canonical cross-platform path relative to one project root."""

    value: str

    def __post_init__(self) -> None:
        _validate_repository_path(self.value)

    @classmethod
    def parse(cls, value: str | PurePosixPath) -> Self:
        """Parse a canonical path without silently normalizing unsafe input."""
        return cls(value.as_posix() if isinstance(value, PurePosixPath) else value)

    @property
    def parts(self) -> tuple[str, ...]:
        return PurePosixPath(self.value).parts

    @property
    def name(self) -> str:
        return self.parts[-1]

    @property
    def parent(self) -> RepositoryPath | None:
        parent = PurePosixPath(self.value).parent.as_posix()
        return None if parent == "." else RepositoryPath(parent)

    def child(self, *segments: str) -> RepositoryPath:
        """Append canonical segments and return a newly validated path."""
        if not segments:
            return self
        return RepositoryPath(PurePosixPath(self.value, *segments).as_posix())

    def __str__(self) -> str:
        return self.value


def _validate_repository_path(value: str) -> None:
    if not isinstance(value, str):
        raise UnsafeProjectPathError("a repository path must be a string")
    if not value or value != value.strip():
        raise UnsafeProjectPathError("a repository path must be non-empty and trimmed")
    if len(value) > _MAX_REPOSITORY_PATH_LENGTH:
        raise UnsafeProjectPathError(
            f"a repository path cannot exceed {_MAX_REPOSITORY_PATH_LENGTH} characters"
        )
    if not value.isascii():
        raise UnsafeProjectPathError("a repository path must contain ASCII characters only")
    if "\\" in value:
        raise UnsafeProjectPathError("a repository path must use forward slashes")

    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise UnsafeProjectPathError("a repository path must be relative and already normalized")

    for segment in path.parts:
        _validate_repository_segment(segment)


def _validate_repository_segment(segment: str) -> None:
    if not segment or len(segment) > _MAX_SEGMENT_LENGTH:
        raise UnsafeProjectPathError(
            f"repository path segments must contain 1 to {_MAX_SEGMENT_LENGTH} characters"
        )
    if segment in {".", ".."}:
        raise UnsafeProjectPathError("repository paths cannot contain dot traversal")
    if any(character not in _ALLOWED_SEGMENT_CHARACTERS for character in segment):
        raise UnsafeProjectPathError(
            "repository path segments may use lowercase letters, digits, dots, "
            "hyphens, and underscores"
        )
    if segment.endswith("."):
        raise UnsafeProjectPathError("repository path segments cannot end with a dot")
    basename = segment.split(".", maxsplit=1)[0]
    if basename in _RESERVED_WINDOWS_NAMES:
        raise UnsafeProjectPathError(f"repository path segment {segment!r} is reserved on Windows")


PROJECT_MARKER = RepositoryPath(".ludowright/project.json")
LOCK_DIRECTORY = RepositoryPath(".ludowright/locks")


@dataclass(frozen=True, slots=True)
class LockMetadata:
    """Diagnostic metadata stored in an exclusive lock file."""

    token: str
    name: str
    pid: int
    hostname: str
    created_at: str

    def to_json(self) -> bytes:
        payload = {
            "created_at": self.created_at,
            "hostname": self.hostname,
            "name": self.name,
            "pid": self.pid,
            "token": self.token,
        }
        return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()

    @classmethod
    def from_json(cls, payload: bytes) -> Self:
        try:
            data = json.loads(payload)
            return cls(
                token=data["token"],
                name=data["name"],
                pid=data["pid"],
                hostname=data["hostname"],
                created_at=data["created_at"],
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ProjectLockOwnershipError("project lock metadata is malformed") from error


class ProjectFilesystem:
    """Filesystem rooted at one canonical, resolved project directory."""

    def __init__(self, root: Path | str) -> None:
        candidate = Path(root).expanduser()
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as error:
            raise ProjectFilesystemError(f"project root does not exist: {candidate}") from error
        if not resolved.is_dir():
            raise ProjectFilesystemError(f"project root is not a directory: {resolved}")
        self._root = resolved

    @property
    def root(self) -> Path:
        return self._root

    @classmethod
    def discover(
        cls,
        start: Path | str,
        *,
        marker: RepositoryPath = PROJECT_MARKER,
    ) -> ProjectFilesystem:
        """Find the nearest ancestor containing a regular project marker file."""
        candidate = Path(start).expanduser()
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as error:
            raise ProjectRootNotFoundError(
                f"cannot discover a project from missing path: {candidate}"
            ) from error
        current = resolved.parent if resolved.is_file() else resolved

        for directory in (current, *current.parents):
            marker_path = directory.joinpath(*marker.parts)
            if os.path.lexists(marker_path):
                marker_stat = os.lstat(marker_path)
                if stat.S_ISLNK(marker_stat.st_mode):
                    raise UnsafeProjectPathError("project marker cannot be a symlink")
                if stat.S_ISREG(marker_stat.st_mode):
                    return cls(directory)
                raise ProjectFilesystemError("project marker must be a regular file")

        raise ProjectRootNotFoundError(f"no {marker.value!r} marker found from {current}")

    def resolve(self, path: RepositoryPath, *, must_exist: bool = False) -> Path:
        """Resolve a repository path without following an escaping symlink."""
        if not isinstance(path, RepositoryPath):
            raise UnsafeProjectPathError("project paths must use RepositoryPath")
        candidate = self._root.joinpath(*path.parts)
        self._assert_lexically_inside(candidate)
        self._assert_safe_existing_prefix(candidate)

        if must_exist:
            if not os.path.lexists(candidate):
                raise FileNotFoundError(candidate)
            candidate_stat = os.lstat(candidate)
            if stat.S_ISLNK(candidate_stat.st_mode):
                raise UnsafeProjectPathError("project paths cannot resolve through symlinks")
        return candidate

    def ensure_directory(
        self,
        path: RepositoryPath,
        *,
        mode: int = 0o755,
    ) -> Path:
        """Create a directory tree while rejecting symlink and file ancestors."""
        target = self._root
        for segment in path.parts:
            target = target / segment
            self._assert_lexically_inside(target)
            if os.path.lexists(target):
                target_stat = os.lstat(target)
                if stat.S_ISLNK(target_stat.st_mode):
                    raise UnsafeProjectPathError(f"directory path contains symlink: {target}")
                if not stat.S_ISDIR(target_stat.st_mode):
                    raise ProjectFilesystemError(
                        f"directory path contains a non-directory: {target}"
                    )
                continue
            try:
                target.mkdir(mode=mode)
            except FileExistsError:
                target_stat = os.lstat(target)
                if stat.S_ISLNK(target_stat.st_mode) or not stat.S_ISDIR(target_stat.st_mode):
                    raise UnsafeProjectPathError(
                        f"directory path changed during creation: {target}"
                    ) from None
        return target

    def read_bytes(
        self,
        path: RepositoryPath,
        *,
        max_bytes: int | None = None,
    ) -> bytes:
        """Read one regular file with an optional size limit."""
        target = self.resolve(path, must_exist=True)
        target_stat = os.lstat(target)
        if not stat.S_ISREG(target_stat.st_mode):
            raise ProjectFilesystemError(f"project path is not a regular file: {path}")
        if max_bytes is not None:
            _validate_size_limit(max_bytes)
            if target_stat.st_size > max_bytes:
                raise ProjectFilesystemError(
                    f"project file exceeds the {max_bytes}-byte read limit: {path}"
                )
        with target.open("rb") as stream:
            payload = stream.read() if max_bytes is None else stream.read(max_bytes + 1)
        if max_bytes is not None and len(payload) > max_bytes:
            raise ProjectFilesystemError(
                f"project file changed beyond the {max_bytes}-byte read limit: {path}"
            )
        return payload

    def read_text(
        self,
        path: RepositoryPath,
        *,
        encoding: str = "utf-8",
        max_bytes: int | None = None,
    ) -> str:
        return self.read_bytes(path, max_bytes=max_bytes).decode(encoding)

    def write_bytes(
        self,
        path: RepositoryPath,
        payload: bytes,
        *,
        mode: int | None = None,
    ) -> Path:
        """Atomically replace a regular file using a sibling temporary file."""
        if not isinstance(payload, bytes):
            raise TypeError("atomic byte writes require an immutable bytes payload")
        target = self.resolve(path)
        parent = self._ensure_parent(path)
        self._assert_safe_write_target(target)

        file_mode = mode if mode is not None else self._existing_or_default_mode(target)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            os.chmod(temporary, file_mode)
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            self._assert_safe_write_target(target)
            os.replace(temporary, target)
            _fsync_directory(parent)
        except BaseException:
            if descriptor >= 0:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)
            raise
        return target

    def write_text(
        self,
        path: RepositoryPath,
        text: str,
        *,
        encoding: str = "utf-8",
        mode: int | None = None,
    ) -> Path:
        if not isinstance(text, str):
            raise TypeError("atomic text writes require a string payload")
        return self.write_bytes(path, text.encode(encoding), mode=mode)

    def remove_file(self, path: RepositoryPath) -> bool:
        """Remove one regular repository file and report whether it existed."""
        target = self.resolve(path)
        if not os.path.lexists(target):
            return False
        target_stat = os.lstat(target)
        if stat.S_ISLNK(target_stat.st_mode):
            raise UnsafeProjectPathError(f"project paths cannot remove symlinks: {path}")
        if not stat.S_ISREG(target_stat.st_mode):
            raise ProjectFilesystemError(f"project path is not a regular file: {path}")
        target.unlink()
        _fsync_directory(target.parent)
        return True

    def lock(
        self,
        name: str,
        *,
        timeout: float = 0.0,
        poll_interval: float = 0.05,
    ) -> ProjectLock:
        """Create an exclusive lock context for one canonical lock name."""
        _validate_lock_name(name)
        _validate_timeout(timeout, "timeout")
        _validate_timeout(poll_interval, "poll interval", strictly_positive=True)
        return ProjectLock(
            filesystem=self,
            name=name,
            timeout=timeout,
            poll_interval=poll_interval,
        )

    def read_lock_metadata(self, name: str) -> LockMetadata | None:
        """Read bounded diagnostic lock metadata without acquiring the lock."""
        _validate_lock_name(name)
        path = LOCK_DIRECTORY.child(f"{name}.lock")
        try:
            payload = self.read_bytes(path, max_bytes=_MAX_LOCK_METADATA_BYTES)
        except FileNotFoundError:
            return None
        return LockMetadata.from_json(payload)

    def _ensure_parent(self, path: RepositoryPath) -> Path:
        return self._root if path.parent is None else self.ensure_directory(path.parent)

    def _assert_lexically_inside(self, candidate: Path) -> None:
        try:
            candidate.relative_to(self._root)
        except ValueError as error:
            raise UnsafeProjectPathError(f"project path escapes the root: {candidate}") from error

    def _assert_safe_existing_prefix(self, candidate: Path) -> None:
        relative = candidate.relative_to(self._root)
        current = self._root
        for segment in relative.parts:
            current = current / segment
            if not os.path.lexists(current):
                return
            current_stat = os.lstat(current)
            if stat.S_ISLNK(current_stat.st_mode):
                raise UnsafeProjectPathError(f"project path contains symlink: {current}")

    def _assert_safe_write_target(self, target: Path) -> None:
        self._assert_lexically_inside(target)
        self._assert_safe_existing_prefix(target)
        if not os.path.lexists(target):
            return
        target_stat = os.lstat(target)
        if stat.S_ISLNK(target_stat.st_mode):
            raise UnsafeProjectPathError("atomic writes cannot replace a symlink")
        if not stat.S_ISREG(target_stat.st_mode):
            raise ProjectFilesystemError("atomic writes require a regular-file target")

    @staticmethod
    def _existing_or_default_mode(target: Path) -> int:
        if not os.path.lexists(target):
            return 0o644
        return stat.S_IMODE(os.lstat(target).st_mode)


class ProjectLock:
    """Exclusive lock backed by an atomically created project-relative file."""

    def __init__(
        self,
        *,
        filesystem: ProjectFilesystem,
        name: str,
        timeout: float,
        poll_interval: float,
    ) -> None:
        self._filesystem = filesystem
        self._name = name
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._metadata: LockMetadata | None = None
        self._device_inode: tuple[int, int] | None = None

    @property
    def metadata(self) -> LockMetadata | None:
        return self._metadata

    @property
    def locked(self) -> bool:
        return self._metadata is not None

    def acquire(self) -> Self:
        if self.locked:
            return self
        lock_directory = self._filesystem.ensure_directory(LOCK_DIRECTORY, mode=0o700)
        lock_path = lock_directory / f"{self._name}.lock"
        deadline = time.monotonic() + self._timeout

        while True:
            metadata = LockMetadata(
                token=uuid.uuid4().hex,
                name=self._name,
                pid=os.getpid(),
                hostname=socket.gethostname(),
                created_at=datetime.now(UTC).isoformat(),
            )
            try:
                descriptor = os.open(
                    lock_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise ProjectLockTimeoutError(
                        f"timed out acquiring project lock {self._name!r}"
                    ) from None
                time.sleep(min(self._poll_interval, max(0.0, deadline - time.monotonic())))
                continue

            try:
                payload = metadata.to_json()
                os.write(descriptor, payload)
                os.fsync(descriptor)
            except BaseException:
                os.close(descriptor)
                lock_path.unlink(missing_ok=True)
                raise
            os.close(descriptor)
            lock_stat = os.lstat(lock_path)
            self._metadata = metadata
            self._device_inode = (lock_stat.st_dev, lock_stat.st_ino)
            return self

    def release(self) -> None:
        if self._metadata is None or self._device_inode is None:
            return
        lock_path = self._filesystem.resolve(
            LOCK_DIRECTORY.child(f"{self._name}.lock"),
            must_exist=True,
        )
        lock_stat = os.lstat(lock_path)
        if (lock_stat.st_dev, lock_stat.st_ino) != self._device_inode:
            raise ProjectLockOwnershipError(
                f"project lock {self._name!r} was replaced by another file"
            )
        current = LockMetadata.from_json(
            self._filesystem.read_bytes(
                LOCK_DIRECTORY.child(f"{self._name}.lock"),
                max_bytes=_MAX_LOCK_METADATA_BYTES,
            )
        )
        if current.token != self._metadata.token:
            raise ProjectLockOwnershipError(
                f"project lock {self._name!r} has a different ownership token"
            )
        lock_path.unlink()
        _fsync_directory(lock_path.parent)
        self._metadata = None
        self._device_inode = None

    def __enter__(self) -> Self:
        return self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()


def _validate_size_limit(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("a file size limit must be a non-negative integer")


def _validate_lock_name(name: str) -> None:
    if not name:
        raise ProjectFilesystemError("project lock name cannot be empty")
    try:
        path = RepositoryPath(f"{name}.lock")
    except UnsafeProjectPathError as error:
        raise ProjectFilesystemError(f"invalid project lock name: {name!r}") from error
    if len(path.parts) != 1 or "." in name or "_" in name:
        raise ProjectFilesystemError(
            "project lock names must use lowercase letters, digits, and hyphens"
        )


def _validate_timeout(
    value: float,
    label: str,
    *,
    strictly_positive: bool = False,
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"lock {label} must be numeric")
    if not math.isfinite(value):
        raise ValueError(f"lock {label} must be finite")
    minimum_valid = value > 0 if strictly_positive else value >= 0
    if not minimum_valid:
        qualifier = "positive" if strictly_positive else "non-negative"
        raise ValueError(f"lock {label} must be {qualifier}")


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
