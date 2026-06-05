from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from apps.api.structura_api.dependencies import require_admin
from lib.config import get_settings
from lib.db.connection import db_connection
from lib.model_runtime.health import (
    configured_model_health_snapshots,
    probed_model_health_snapshots,
)

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


@router.get("/service-health")
def service_health(_principal: Annotated[object, Depends(require_admin)]) -> dict[str, object]:
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
    by_name = {row["service_name"]: row for row in rows}
    settings = get_settings()
    model_snapshots = (
        configured_model_health_snapshots(settings, include_queue_metrics=True)
        if settings.model_mode == "fixture"
        else probed_model_health_snapshots(settings, include_queue_metrics=True)
    )
    for snapshot in model_snapshots:
        by_name[snapshot["service_name"]] = snapshot
    return {"items": list(by_name.values())}
