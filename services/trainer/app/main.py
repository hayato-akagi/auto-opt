import asyncio
import random
from datetime import datetime, timezone

from fastapi import FastAPI

try:
    import torch
except ImportError:  # pragma: no cover - depends on runtime image/env
    torch = None
from .models import (
    HealthResponse,
    TrainRequest,
    TrainJobResponse,
    TrainJobListResponse,
    TrainJobStatus,
    TrainMetrics,
    EpochLog,
    BenchmarkResultDetail,
)

app = FastAPI(title="trainer", version="0.1.0")

# In-memory training job storage for testing
_jobs: dict[str, TrainJobStatus] = {}
_job_counter = 0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_benchmark(final_loss: float) -> dict[str, BenchmarkResultDetail]:
    # Lightweight synthetic benchmark derived from final loss.
    base = max(min(final_loss, 1.0), 0.001)
    new_med = 0.03 + base * 0.10
    cur_med = new_med * 1.3
    new_p95 = new_med * 1.8
    cur_p95 = cur_med * 1.8
    return {
        "new_model": BenchmarkResultDetail(
            median_final_error_mm=new_med,
            p95_final_error_mm=new_p95,
            converge_rate=0.92,
            trial_errors_mm=[new_med * x for x in [0.7, 0.9, 1.0, 1.2, 1.4]],
            benchmark_trial_ids=["trial_001", "trial_002", "trial_003", "trial_004", "trial_005"],
        ),
        "current_model": BenchmarkResultDetail(
            median_final_error_mm=cur_med,
            p95_final_error_mm=cur_p95,
            converge_rate=0.88,
            trial_errors_mm=[cur_med * x for x in [0.7, 0.9, 1.0, 1.2, 1.4]],
            benchmark_trial_ids=["trial_001", "trial_002", "trial_003", "trial_004", "trial_005"],
        ),
    }


async def _run_training_job(train_job_id: str, request: TrainRequest) -> None:
    """Background trainer loop that updates epoch/loss progress in-memory."""
    try:
        epoch_losses: list[float] = []
        total_epochs = request.epochs
        batch_size = request.batch_size

        if torch is not None:
            # Tiny synthetic dataset and small model for fast demo behavior.
            x = torch.linspace(-1.0, 1.0, 256).unsqueeze(1)
            y = 2.0 * x + 0.3 * torch.sin(3 * x)
            y = y + 0.05 * torch.randn_like(y)

            if request.model_type == "baseline_only":
                model = torch.nn.Linear(1, 1)
            else:
                model = torch.nn.Sequential(
                    torch.nn.Linear(1, 16),
                    torch.nn.ReLU(),
                    torch.nn.Linear(16, 8),
                    torch.nn.ReLU(),
                    torch.nn.Linear(8, 1),
                )

            optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
            criterion = torch.nn.MSELoss()
            data_size = x.shape[0]
        else:
            x = y = model = optimizer = criterion = data_size = None

        for epoch in range(1, total_epochs + 1):
            if torch is not None:
                perm = torch.randperm(data_size)
                epoch_loss = 0.0
                batch_count = 0

                for i in range(0, data_size, batch_size):
                    idx = perm[i : i + batch_size]
                    xb = x[idx]
                    yb = y[idx]

                    pred = model(xb)
                    loss = criterion(pred, yb)
                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()

                    epoch_loss += float(loss.detach().cpu())
                    batch_count += 1

                epoch_loss /= max(batch_count, 1)
            else:
                # Fallback: monotonic-ish loss curve for environments without torch.
                base = 0.8 * (0.96 ** (epoch - 1))
                jitter = random.uniform(-0.01, 0.01)
                epoch_loss = max(base + jitter, 0.001)
            epoch_losses.append(epoch_loss)

            job = _jobs[train_job_id]
            job.current_epoch = epoch
            job.last_loss = epoch_loss
            job.progress_rate = epoch / total_epochs
            job.updated_at = _utc_now_iso()
            job.epoch_logs.append(
                EpochLog(
                    epoch=epoch,
                    loss=epoch_loss,
                    timestamp=job.updated_at,
                )
            )
            _jobs[train_job_id] = job

            # Make intermediate updates visible to polling clients.
            await asyncio.sleep(0.15)

        final_loss = epoch_losses[-1] if epoch_losses else 0.0
        done = _jobs[train_job_id]
        done.status = "completed"
        done.progress_rate = 1.0
        done.updated_at = _utc_now_iso()
        done.train_metrics = TrainMetrics(
            epoch_losses=epoch_losses,
            final_train_loss=final_loss,
            epochs=total_epochs,
        )
        done.benchmark_results = _make_benchmark(final_loss)
        done.promoted = True
        done.promoted_version = f"v{train_job_id}"
        _jobs[train_job_id] = done

    except Exception as exc:  # pragma: no cover - defensive for runtime issues
        failed = _jobs.get(train_job_id)
        if failed is None:
            return
        failed.status = "failed"
        failed.updated_at = _utc_now_iso()
        failed.error_message = str(exc)
        _jobs[train_job_id] = failed


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/train", response_model=TrainJobResponse)
async def start_training(request: TrainRequest) -> TrainJobResponse:
    """Start a new training job."""
    global _job_counter
    _job_counter += 1
    train_job_id = f"train_job_{_job_counter:06d}"
    
    # Initialize job with "running" status
    job = TrainJobStatus(
        train_job_id=train_job_id,
        status="running",
        data_stats={"experiment_count": len(request.experiment_ids)},
        started_at=_utc_now_iso(),
        updated_at=_utc_now_iso(),
        total_epochs=request.epochs,
        current_epoch=0,
        progress_rate=0.0,
        last_loss=None,
        epoch_logs=[],
        train_metrics=None,
        benchmark_results=None,
        promoted=None,
        promoted_version=None,
    )
    _jobs[train_job_id] = job

    asyncio.create_task(_run_training_job(train_job_id, request))
    
    return TrainJobResponse(
        train_job_id=train_job_id,
        status="running",
        message=f"Training job {train_job_id} started",
    )


@app.get("/train", response_model=TrainJobListResponse)
async def list_training_jobs() -> TrainJobListResponse:
    """List all training jobs."""
    jobs = list(_jobs.values())
    return TrainJobListResponse(jobs=jobs)


@app.get("/train/{train_job_id}", response_model=TrainJobStatus)
async def get_training_job_status(train_job_id: str) -> TrainJobStatus:
    """Get status of a training job."""
    if train_job_id not in _jobs:
        # Keep backward-compatible response shape but return explicit failure.
        return TrainJobStatus(
            train_job_id=train_job_id,
            status="failed",
            error_message="train_job_id not found",
        )
    
    return _jobs[train_job_id]
