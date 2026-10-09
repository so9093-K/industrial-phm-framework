"""Cooperative process-wide Web mutation lock using the supervisor's workspace lease.

The opt-in Web preview may read while the normal Operations node runs.
Mutations must never race the supervisor-owned marimo UI or another Web
preview: both processes coordinate through the same POSIX advisory lock.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - the supported node reference is POSIX
    fcntl = None  # type: ignore[assignment]

from industrial_phm.runtime.operations_web_setup import SourceControlConflict
from industrial_phm.runtime.operations_workspace import OperationsWorkspace


@contextmanager
def web_workspace_writer(root: Path) -> Iterator[None]:
    """Hold the exact supervisor workspace lease for one authorized Web mutation.

    This guard intentionally never writes or truncates the supervisor PID marker.
    Failure is a conflict, not a stale PID heuristic. It coordinates cooperating
    supervisors and Web preview processes; direct uncoordinated file edits remain
    outside the supported single-writer contract.
    """
    if fcntl is None:
        raise SourceControlConflict("POSIX workspace writer locking unavailable")
    lease_path = OperationsWorkspace(root).supervisor_lock_path
    lease_path.parent.mkdir(parents=True, exist_ok=True)
    with lease_path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise SourceControlConflict("workspace already owned by another writer") from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
