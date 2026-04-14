from fastapi import FastAPI

from .core import apply_bolt
from .models import BoltApplyRequest, BoltResult, HealthResponse

app = FastAPI(title="bolt-service", version="0.1.0")


@app.post("/bolt/apply", response_model=BoltResult)
async def apply_bolt_endpoint(payload: BoltApplyRequest) -> BoltResult:
    return apply_bolt(
        torque_upper=payload.torque_upper,
        torque_lower=payload.torque_lower,
        bolt_model=payload.bolt_model,
        random_seed=payload.random_seed,
    )


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="bolt-service", version="0.1.0")
