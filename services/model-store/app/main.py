from datetime import datetime
from fastapi import FastAPI, HTTPException
from .models import (
    HealthResponse,
    ModelMeta,
    ModelListResponse,
    ModelPromoteRequest,
    ModelPromoteResponse,
)

app = FastAPI(title="model-store", version="0.1.0")

# In-memory model storage for testing
_models: dict[str, ModelMeta] = {}
_current_version: str | None = None


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/models", response_model=ModelMeta)
async def register_model(model: ModelMeta) -> ModelMeta:
    """Register a new model version."""
    if model.version in _models:
        raise HTTPException(status_code=409, detail=f"Model {model.version} already exists")
    
    _models[model.version] = model
    return model


@app.get("/models", response_model=ModelListResponse)
async def list_models() -> ModelListResponse:
    """List all registered models."""
    models = list(_models.values())
    return ModelListResponse(models=models, current_version=_current_version)


@app.get("/models/{version}", response_model=ModelMeta)
async def get_model(version: str) -> ModelMeta:
    """Get metadata for a specific model version."""
    if version not in _models:
        raise HTTPException(status_code=404, detail=f"Model {version} not found")
    
    return _models[version]


@app.post("/models/{version}/promote", response_model=ModelPromoteResponse)
async def promote_model(version: str, request: ModelPromoteRequest) -> ModelPromoteResponse:
    """Promote a model to 'current' status."""
    if version != request.version:
        raise HTTPException(status_code=400, detail="Version mismatch")
    
    if version not in _models:
        raise HTTPException(status_code=404, detail=f"Model {version} not found")
    
    model = _models[version]
    promoted_at = datetime.utcnow().isoformat() + "Z"
    model.status = "current"
    model.promoted_at = promoted_at
    
    # Demote previous current version
    global _current_version
    if _current_version and _current_version != version and _current_version in _models:
        _models[_current_version].status = "archived"
    
    _current_version = version
    
    return ModelPromoteResponse(
        version=version,
        new_status="current",
        promoted_at=promoted_at,
    )

