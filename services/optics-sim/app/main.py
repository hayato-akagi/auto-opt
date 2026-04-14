from fastapi import FastAPI, HTTPException

from .models import HealthResponse, SimulationRequest, SimulationResponse
from .simulation import SimulationError, run_simulation

app = FastAPI(title="optics-sim", version="0.1.0")


@app.post("/simulate", response_model=SimulationResponse)
async def simulate(payload: SimulationRequest) -> SimulationResponse:
    try:
        return run_simulation(payload)
    except SimulationError as exc:
        raise HTTPException(status_code=500, detail=f"simulation failed: {exc}") from exc


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="optics-sim", version="0.1.0")
