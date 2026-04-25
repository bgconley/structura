from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.structura_api.dependencies import current_principal, require_admin, require_admin_csrf
from lib.auth import AuthPrincipal
from lib.contracts import AcceptedJob, JobState
from lib.jobs import JobService, JobServiceError

router = APIRouter(prefix="/api/v1", tags=["Jobs"])


@router.get("/jobs/{jobId}", response_model=JobState)
def get_job(
    jobId: UUID,
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> JobState:
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    job = JobService().get_job(jobId, household_id=principal.household_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.get("/admin/jobs", tags=["Admin"])
def list_admin_jobs(
    principal: Annotated[AuthPrincipal, Depends(require_admin)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    job_type: Annotated[str | None, Query(alias="jobType")] = None,
) -> dict[str, list[JobState]]:
    return {
        "items": JobService().list_jobs(
            household_id=principal.household_id,
            status=status_filter,
            job_type=job_type,
        )
    }


@router.post(
    "/admin/jobs/{jobId}/retry",
    response_model=AcceptedJob,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Admin"],
)
def retry_job(
    jobId: UUID,
    principal: Annotated[AuthPrincipal, Depends(require_admin_csrf)],
) -> AcceptedJob:
    try:
        return JobService().retry_job(job_id=jobId, household_id=principal.household_id)
    except JobServiceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
