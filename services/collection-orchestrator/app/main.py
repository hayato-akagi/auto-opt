from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query

from .clients import ControllerClient
from .config import Settings
from .job_runner import run_collection_job
from .models import (
    CollectionJobCreateRequest,
    HealthResponse,
    JobCreateResponse,
    JobListResponse,
    JobStatusResponse,
)
from .storage import InMemoryJobStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_job_id(counter: int) -> str:
    now = datetime.now(timezone.utc)
    return f"cjob_{now:%Y%m%d_%H%M%S}_{counter:04d}"


def create_app(
    settings: Settings | None = None,
    store: InMemoryJobStore | None = None,
    controller_client: ControllerClient | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    resolved_store = store or InMemoryJobStore()
    resolved_client = controller_client or ControllerClient(
        simple_controller_url=resolved_settings.simple_controller_url,
        ai_controller_url=resolved_settings.ai_controller_url,
        timeout_sec=resolved_settings.downstream_timeout_sec,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await resolved_client.close()

    app = FastAPI(title="collection-orchestrator", version="0.1.0", lifespan=lifespan)
    app.state._job_counter = 0

    @app.post("/jobs", response_model=JobCreateResponse, status_code=202)
    async def create_job(payload: CollectionJobCreateRequest) -> JobCreateResponse:
        app.state._job_counter += 1
        job_id = payload.job_id or _generate_job_id(app.state._job_counter)

        total_tasks = sum(len(t.seeds) for t in payload.tasks)
        if total_tasks == 0:
            raise HTTPException(status_code=422, detail="tasks/seeds must include at least one execution")

        job = {
            "job_id": job_id,
            "algorithm": payload.algorithm,
            "status": "running",
            "total_tasks": total_tasks,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "started_at": _now_iso(),
            "finished_at": None,
            "task_results": [],
        }
        try:
            resolved_store.create(job_id, job)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        req = payload.model_copy(update={"max_workers": payload.max_workers or resolved_settings.max_workers})
        asyncio.create_task(
            run_collection_job(
                job_id=job_id,
                request=req,
                store=resolved_store,
                client=resolved_client,
            )
        )

        return JobCreateResponse(
            job_id=job_id,
            status="running",
            total_tasks=total_tasks,
            created_at=job["started_at"],
        )

    @app.get("/jobs/{job_id}", response_model=JobStatusResponse)
    async def get_job(job_id: str) -> JobStatusResponse:
        job = resolved_store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
        return JobStatusResponse.model_validate(job)

    @app.get("/jobs", response_model=JobListResponse)
    async def list_jobs(status: str | None = Query(default=None)) -> JobListResponse:
        jobs = resolved_store.list(status=status)
        return JobListResponse(jobs=[JobStatusResponse.model_validate(j) for j in jobs])

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service="collection-orchestrator", version="0.1.0")

    return app


app = create_app()
