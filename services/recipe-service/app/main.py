from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .clients import DownstreamClients
from .config import Settings
from .errors import (
    DownstreamServiceError,
    ResourceNotFoundError,
    TrialAlreadyCompletedError,
)
from .models import (
    CompleteTrialResponse,
    ExperimentCreateRequest,
    ExperimentCreateResponse,
    ExperimentListResponse,
    HealthResponse,
    StepExecuteRequest,
    StepExecuteResponse,
    StepImageRequest,
    StepImagesResponse,
    StepListResponse,
    StepRecord,
    SweepRequest,
    SweepResponse,
    TrialCreateResponse,
    TrialListResponse,
    TrialStartRequest,
)
from .orchestrator import RecipeOrchestrator
from .storage import RecipeStorage


def create_app(
    settings: Settings | None = None,
    storage: RecipeStorage | None = None,
    clients: DownstreamClients | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    resolved_storage = storage or RecipeStorage(resolved_settings.data_dir)
    resolved_clients = clients or DownstreamClients(
        optics_sim_kraken_url=resolved_settings.optics_sim_kraken_url,
        optics_sim_simple_url=resolved_settings.optics_sim_simple_url,
        position_service_url=resolved_settings.position_service_url,
        bolt_service_url=resolved_settings.bolt_service_url,
        timeout_sec=resolved_settings.downstream_timeout_sec,
    )
    orchestrator = RecipeOrchestrator(resolved_storage, resolved_clients)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        close = getattr(resolved_clients, "close", None)
        if callable(close):
            await close()

    app = FastAPI(title="recipe-service", version="0.1.0", lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.storage = resolved_storage
    app.state.clients = resolved_clients
    app.state.orchestrator = orchestrator

    @app.exception_handler(ResourceNotFoundError)
    async def handle_not_found(_: Any, exc: ResourceNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": exc.detail})

    @app.exception_handler(TrialAlreadyCompletedError)
    async def handle_conflict(_: Any, exc: TrialAlreadyCompletedError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": exc.detail})

    @app.exception_handler(DownstreamServiceError)
    async def handle_downstream(_: Any, exc: DownstreamServiceError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "downstream": exc.downstream},
        )

    @app.post("/experiments", status_code=201, response_model=ExperimentCreateResponse)
    async def create_experiment(payload: ExperimentCreateRequest) -> ExperimentCreateResponse:
        created = await resolved_storage.create_experiment(payload)
        return ExperimentCreateResponse(**created)

    @app.get("/experiments", response_model=ExperimentListResponse)
    async def list_experiments() -> ExperimentListResponse:
        experiments = await resolved_storage.list_experiments()
        return ExperimentListResponse(experiments=experiments)

    @app.get("/experiments/{experiment_id}", response_model=dict[str, Any])
    async def get_experiment(experiment_id: str) -> dict[str, Any]:
        return await resolved_storage.get_experiment(experiment_id)

    @app.post(
        "/experiments/{experiment_id}/trials",
        status_code=201,
        response_model=TrialCreateResponse,
    )
    async def create_trial(
        experiment_id: str,
        payload: TrialStartRequest,
    ) -> TrialCreateResponse:
        trial = await resolved_storage.create_trial(
            experiment_id,
            mode=payload.mode,
            control=payload.control,
        )
        return TrialCreateResponse(**trial)

    @app.get("/experiments/{experiment_id}/trials", response_model=TrialListResponse)
    async def list_trials(experiment_id: str) -> TrialListResponse:
        trials = await resolved_storage.list_trials(experiment_id)
        return TrialListResponse(trials=trials)

    @app.get("/experiments/{experiment_id}/trials/{trial_id}", response_model=dict[str, Any])
    async def get_trial(experiment_id: str, trial_id: str) -> dict[str, Any]:
        return await resolved_storage.get_trial_detail(experiment_id, trial_id)

    @app.post(
        "/experiments/{experiment_id}/trials/{trial_id}/steps",
        response_model=StepExecuteResponse,
    )
    async def execute_step(
        experiment_id: str,
        trial_id: str,
        payload: StepExecuteRequest,
    ) -> StepExecuteResponse:
        result = await orchestrator.execute_step(experiment_id, trial_id, payload)
        return StepExecuteResponse(**result)

    @app.get(
        "/experiments/{experiment_id}/trials/{trial_id}/steps",
        response_model=StepListResponse,
    )
    async def list_steps(experiment_id: str, trial_id: str) -> StepListResponse:
        steps = await resolved_storage.list_steps(experiment_id, trial_id)
        return StepListResponse(steps=steps)

    @app.get(
        "/experiments/{experiment_id}/trials/{trial_id}/steps/{step_index}",
        response_model=StepRecord,
    )
    async def get_step(
        experiment_id: str,
        trial_id: str,
        step_index: int,
    ) -> StepRecord:
        step = await resolved_storage.get_step(experiment_id, trial_id, step_index)
        return StepRecord(**step)

    @app.post(
        "/experiments/{experiment_id}/trials/{trial_id}/complete",
        response_model=CompleteTrialResponse,
    )
    async def complete_trial(
        experiment_id: str,
        trial_id: str,
    ) -> CompleteTrialResponse:
        summary = await orchestrator.complete_trial(experiment_id, trial_id)
        return CompleteTrialResponse(**summary)

    @app.post(
        "/experiments/{experiment_id}/trials/{trial_id}/steps/{step_index}/images",
        response_model=StepImagesResponse,
    )
    async def get_step_images(
        experiment_id: str,
        trial_id: str,
        step_index: int,
        payload: StepImageRequest,
    ) -> StepImagesResponse:
        images = await orchestrator.get_step_images(
            experiment_id,
            trial_id,
            step_index,
            payload.phase,
        )
        return StepImagesResponse(**images)

    @app.post("/recipes/sweep", response_model=SweepResponse)
    async def run_sweep(payload: SweepRequest) -> SweepResponse:
        result = await orchestrator.run_sweep(payload)
        return SweepResponse(**result)

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service="recipe-service", version="0.1.0")

    return app


app = create_app()
