from __future__ import annotations

from lib.jobs.errors import JobOwnershipLost


class ProcessingError(Exception):
    """Static, source-free processing contract failure."""


class ProcessingAuthorityLost(JobOwnershipLost):
    """A valid queue attempt no longer owns the requested document generation."""


class CheckpointConflict(ProcessingError):
    """The same immutable identity was submitted with different content."""
