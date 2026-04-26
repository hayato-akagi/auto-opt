from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .clients import RecipeClient
from .config import Settings
from .errors import DownstreamServiceError, UnsupportedAlgorithmError
from .logic import compute_step
from .models import (
    AlgorithmsResponse,
    AlgorithmDescription,
    ControlRunRequest,
    ControlRunResponse,
    ControlStepRequest,
    ControlStepResponse,
    HealthResponse,
)
from .runner import run_control_loop

SUPPORTED_ALGORITHM = "simple-controller"


def create_app(
    settings: Settings | None = None,
    recipe_client: RecipeClient | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    resolved_client = recipe_client or RecipeClient(
        recipe_service_url=resolved_settings.recipe_service_url,
        timeout_sec=resolved_settings.downstream_timeout_sec,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        close = getattr(resolved_client, "close", None)
        if callable(close):
            await close()

    app = FastAPI(title="simple-controller", version="0.1.0", lifespan=lifespan)

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
        result = await run_control_loop(payload, resolved_client)
        return result

    @app.post("/control/step", response_model=ControlStepResponse)
    async def control_step(payload: ControlStepRequest) -> ControlStepResponse:
        ensure_supported(payload.algorithm)
        return compute_step(payload)

    @app.get("/control/algorithms", response_model=AlgorithmsResponse)
    async def control_algorithms() -> AlgorithmsResponse:
        return AlgorithmsResponse(
            algorithms=[
                AlgorithmDescription(
                    name=SUPPORTED_ALGORITHM,
                    description="相対操作量を返すシンプル制御器",
                    config_schema={"type": "object"},
                )
            ]
        )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service="simple-controller", version="0.1.0")

    return app


app = create_app()
