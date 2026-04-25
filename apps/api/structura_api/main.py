from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import Depends, FastAPI
from starlette.requests import Request
from starlette.responses import Response

from apps.api.structura_api import __version__
from apps.api.structura_api.dependencies import current_principal
from apps.api.structura_api.routes_admin import router as admin_router
from apps.api.structura_api.routes_auth import router as auth_router
from apps.api.structura_api.routes_documents import router as documents_router
from apps.api.structura_api.routes_jobs import router as jobs_router
from lib.config import get_settings
from lib.contracts import ContractRegistry
from lib.db.migrations import baseline_migration_plan
from lib.observability import configure_logging, log_event


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    app = FastAPI(
        title="Structura API",
        version=__version__,
        summary="Local-first document workbench API",
    )

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next) -> Response:
        correlation_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response = cast(Response, await call_next(request))
        response.headers["X-Request-ID"] = correlation_id
        log_event(
            "api.request",
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
        )
        return response

    @app.get("/healthz", tags=["Health"], include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "api"}

    @app.get("/api/v1/health", tags=["Health"])
    def api_health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    @app.get("/api/v1/version", tags=["Health"])
    def version() -> dict[str, str]:
        return {
            "service": "structura-api",
            "version": __version__,
            "api_contract_version": "0.1.3",
        }

    @app.get("/api/v1/contracts/summary", tags=["Contracts"])
    def contract_summary() -> dict[str, object]:
        registry = ContractRegistry.from_settings(settings)
        return registry.summary()

    @app.get("/api/v1/migrations/baseline", tags=["Admin"])
    def migration_summary(
        _principal: Annotated[object, Depends(current_principal)],
    ) -> dict[str, object]:
        plan = baseline_migration_plan(settings.database_dir)
        return {
            "database_dir": str(settings.database_dir),
            "scripts": [script.name for script in plan.scripts],
        }

    app.include_router(auth_router)
    app.include_router(documents_router)
    app.include_router(jobs_router)
    app.include_router(admin_router)

    return app


app = create_app()
