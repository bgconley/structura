from lib.jobs.errors import JobOwnershipLost


class IndexCandidateError(Exception):
    """Static, content-free candidate contract error."""


class IndexAuthorityLost(JobOwnershipLost):
    """The claimed job no longer owns this candidate index build."""


class IndexCheckpointConflict(IndexCandidateError):
    """An immutable candidate identity was reused with different content."""
