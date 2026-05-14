from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .clients import RecipeClient
from .config import Settings
from .errors import DownstreamServiceError, UnsupportedAlgorithmError
from .model import ModelManager
from .models import (
    ControlRunRequest,
    ControlRunResponse,
    HealthResponse,
    ModelReloadResponse,
    ModelStatusResponse,
)
from .runner import run_control_loop

SUPPORTED_ALGORITHM = "ai-controller"


def create_app(
    settings: Settings | None = None,
    recipe_client: RecipeClient | None = None,
    model_manager: ModelManager | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    resolved_client = recipe_client or RecipeClient(
        recipe_service_url=resolved_settings.recipe_service_url,
        timeout_sec=resolved_settings.downstream_timeout_sec,
    )
    resolved_model_manager = model_manager or ModelManager(
        model_type=resolved_settings.default_model_type,
        model_version=resolved_settings.default_model_version,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        close = getattr(resolved_client, "close", None)
        if callable(close):
            await close()

    app = FastAPI(title="ai-controller", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(DownstreamServiceError)
    async def handle_downstream(_: Any, exc: DownstreamServiceError) -> JSONResponse:
        content = {"detail": exc.detail, "downstream": exc.downstream}
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.exception_handler(UnsupportedAlgorithmError)
    async def handle_algorithm(_: Any, exc: UnsupportedAlgorithmError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": exc.detail})

    def ensure_supported(algorithm: str) -> None:
        if algorithm != SUPPORTED_ALGORITHM:
            raise UnsupportedAlgorithmError(algorithm)

    @app.post("/control/run", response_model=ControlRunResponse)
    async def control_run(payload: ControlRunRequest) -> ControlRunResponse:
        ensure_supported(payload.algorithm)
        if payload.config.model_version is None:
            status = resolved_model_manager.status()
            payload.config.model_version = status.get("loaded_version")
            payload.config.model_type = str(status.get("model_type") or payload.config.model_type)
        result = await run_control_loop(payload, resolved_client)
        return result

    @app.post("/model/reload", response_model=ModelReloadResponse)
    async def model_reload() -> ModelReloadResponse:
        loaded = resolved_model_manager.reload(
            model_type=resolved_settings.default_model_type,
            model_version=resolved_settings.default_model_version,
        )
        return ModelReloadResponse(
            loaded_version=loaded.get("loaded_version"),
            model_type=str(loaded.get("model_type") or "baseline_only"),
        )

    @app.get("/model/status", response_model=ModelStatusResponse)
    async def model_status() -> ModelStatusResponse:
        status = resolved_model_manager.status()
        return ModelStatusResponse(
            loaded_version=status.get("loaded_version"),
            model_type=str(status.get("model_type") or "baseline_only"),
            loaded_at=str(status.get("loaded_at")),
            device=str(status.get("device") or "cpu"),
        )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service="ai-controller", version="0.1.0")

    return app


app = create_app()
