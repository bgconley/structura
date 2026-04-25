from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from apps.api.structura_api.dependencies import current_principal
from lib.db.connection import db_connection

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


@router.get("/service-health")
def service_health(_principal: Annotated[object, Depends(current_principal)]) -> dict[str, object]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (service_name)
                  service_name,
                  status,
                  metrics_json,
                  checked_at
                FROM service_health_snapshots
                ORDER BY service_name, checked_at DESC
                """
            )
            rows = cur.fetchall()
    return {"items": rows}
