from fastapi import FastAPI

from .core import apply_position
from .models import HealthResponse, PositionApplyRequest, PositionApplyResponse

app = FastAPI(title="position-service", version="0.1.0")


@app.post("/position/apply", response_model=PositionApplyResponse)
async def apply_position_endpoint(payload: PositionApplyRequest) -> PositionApplyResponse:
    coll_x_shift, coll_y_shift = apply_position(payload.coll_x, payload.coll_y)
    return PositionApplyResponse(
        coll_x_shift=coll_x_shift,
        coll_y_shift=coll_y_shift,
    )


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="position-service", version="0.1.0")
