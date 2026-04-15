from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .models import HealthResponse, SimulationRequest, SimulationResponse
from .simulation import run_simulation


app = FastAPI(title="simple-optics-sim", version="0.1.0")


@app.post("/simulate", response_model=SimulationResponse)
async def simulate(request: SimulationRequest) -> SimulationResponse:
    """
    Run Gaussian-based optical simulation.
    
    Simple model using Gaussian distribution for spot calculation.
    Much faster than KrakenOS ray tracing but less accurate.
    """
    return run_simulation(request)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        service="simple-optics-sim",
        version="0.1.0"
    )


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "service": "simple-optics-sim",
        "version": "0.1.0",
        "description": "Gaussian-based optical simulation",
    }
