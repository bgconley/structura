from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from lib.contracts import JobState
from lib.jobs.models import ClaimedJob
from lib.jobs.public_errors import public_job_error
from lib.jobs.public_results import public_job_result


def job_state_from_row(row: Mapping[str, Any]) -> JobState:
    error_json = row.get("error_json") or {}
    result_json = row.get("result_json") or {}
    return JobState.model_validate(
        {
            "jobId": row["id"],
            "jobType": row["job_type"],
            "status": row["status"],
            "createdAt": row["created_at"],
            "startedAt": row.get("started_at"),
            "finishedAt": row.get("finished_at"),
            "errorMessage": public_job_error(error_json),
            "lineageRevokedAt": row.get("lineage_revoked_at"),
            "result": public_job_result(result_json),
        }
    )


def claimed_job_from_row(row: Mapping[str, Any]) -> ClaimedJob:
    payload = row.get("payload_json") or {}
    return ClaimedJob(
        state=job_state_from_row(row),
        payload=dict(payload) if isinstance(payload, Mapping) else {},
        document_id=cast(UUID | None, row.get("document_id")),
        household_id=cast(UUID | None, row.get("household_id")),
        claim_token=UUID(str(row["claim_token"])),
        lease_expires_at=cast(datetime, row["lease_expires_at"]),
        attempt_count=int(row["attempt_count"]),
        max_attempts=int(row["max_attempts"]),
    )
