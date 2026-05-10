from fastapi import FastAPI
from .models import HealthResponse

app = FastAPI(title="ai-controller", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
