from __future__ import annotations


class JobServiceError(Exception):
    pass


class PayloadSafetyError(JobServiceError):
    pass


class JobOwnershipLost(JobServiceError):
    """The attempt cannot renew, publish, or change the durable job lifecycle."""
